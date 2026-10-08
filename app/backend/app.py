import datetime
import decimal
import logging
import os
import uuid
from functools import wraps

import jwt
from flask import Flask, jsonify, request
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from mysql.connector import IntegrityError
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

import observability
from db import execute, query, transaction, update_row

log = logging.getLogger("gym.app")


# Makes dates come out as "2026-09-20" and money as plain numbers in the JSON responses
class GymJSONProvider(DefaultJSONProvider):
    @staticmethod
    def default(o):
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        if isinstance(o, decimal.Decimal):
            return float(o)
        return DefaultJSONProvider.default(o)


DEFAULT_SECRET_KEYS = {"", "dev-secret-key-change-in-production", "change-this-secret-key", "changeme"}


# Returns the key used to sign login tokens. In production a real random key is mandatory,
# so the service refuses to start with a known default instead of running insecurely.
def load_secret_key(env):
    key = env.get("SECRET_KEY", "")
    if env.get("APP_ENV") == "production":
        if key in DEFAULT_SECRET_KEYS or len(key) < 32:
            raise RuntimeError("SECRET_KEY must be a random value of at least 32 characters when APP_ENV=production")
        return key
    return key or "dev-secret-key-change-in-production"


app = Flask(__name__)
app.json = GymJSONProvider(app)
CORS(app)
app.config["SECRET_KEY"] = load_secret_key(os.environ)
observability.init_app(app)

PAYMENT_METHODS = {"Card", "UPI", "NetBanking"}


# Checks the Authorization header for a valid JWT with the required role ("member" or "admin")
# before letting a route run. The route receives the decoded token as its first argument.
def auth_required(role):
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            auth_header = request.headers.get("Authorization")
            if not auth_header:
                return jsonify({"error": "Token is missing"}), 401
            try:
                token = auth_header.split(" ")[1]  # "Bearer <token>" -> take the token part
                payload = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
            except Exception:
                return jsonify({"error": "Token is invalid or expired"}), 401
            if payload.get("role") != role:
                return jsonify({"error": f"{role.capitalize()}s only"}), 403
            return f(payload, *args, **kwargs)
        return decorated
    return wrapper


def make_token(id_field, id_value, role):
    return jwt.encode({
        id_field: id_value,
        "role": role,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=6)
    }, app.config["SECRET_KEY"], algorithm="HS256")


# Returns the names of any required fields that are missing/blank in the request body
def missing_fields(data, fields):
    return [f for f in fields if not str(data.get(f) or "").strip()]


# Any Active membership whose end date has passed becomes Expired. Called before every
# read that shows membership status, so statuses are always current without a background job.
def expire_memberships():
    execute("UPDATE memberships SET status = 'Expired' WHERE status = 'Active' AND end_date < CURDATE()")


# Members whose latest (Active, else most recently Expired) membership is shown next to their profile
MEMBER_LIST_SQL = """
    SELECT u.user_id, u.name, u.email, u.phone, u.address, u.created_at,
           m.status AS membership_status, m.end_date, p.name AS plan_name
    FROM users u
    LEFT JOIN memberships m ON m.membership_id = (
        SELECT m2.membership_id FROM memberships m2
        WHERE m2.user_id = u.user_id AND m2.status IN ('Active', 'Expired')
        ORDER BY (m2.status = 'Active') DESC, m2.end_date DESC LIMIT 1
    )
    LEFT JOIN membership_plans p ON p.plan_id = m.plan_id
"""

# Members whose membership has lapsed and who have no currently active one
EXPIRED_SQL = """
    SELECT u.user_id, u.name, u.email, u.phone, p.name AS plan_name, m.end_date,
           DATEDIFF(CURDATE(), m.end_date) AS days_expired
    FROM memberships m
    JOIN users u ON u.user_id = m.user_id
    JOIN membership_plans p ON p.plan_id = m.plan_id
    WHERE m.status = 'Expired'
      AND m.end_date = (SELECT MAX(m2.end_date) FROM memberships m2
                        WHERE m2.user_id = m.user_id AND m2.status IN ('Active', 'Expired'))
      AND NOT EXISTS (SELECT 1 FROM memberships m3 WHERE m3.user_id = m.user_id AND m3.status = 'Active')
    ORDER BY m.end_date DESC
"""


# --- ERROR HANDLING ---

# Every error leaves the API as JSON, so the frontend can always read the "error" field
@app.errorhandler(HTTPException)
def handle_http_error(error):
    return jsonify({"error": error.description or error.name}), error.code


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    log.error("unhandled exception", exc_info=error)
    return jsonify({"error": "Internal server error"}), 500


# --- HEALTH ---

# Liveness: "is the process alive?" Never touches the database, so a database outage
# cannot make an orchestrator kill a perfectly healthy API container.
@app.route("/api/health", methods=["GET"])
@app.route("/api/health/live", methods=["GET"])
def health_live():
    return jsonify({"status": "ok", "message": "Gym Membership Portal API is running"})


# Readiness: "can it serve traffic?" Fails while the database is unreachable,
# which tells a load balancer / Kubernetes to stop sending requests to this instance.
@app.route("/api/health/ready", methods=["GET"])
def health_ready():
    try:
        query("SELECT 1 AS ok", one=True)
    except Exception:
        observability.log_event(log, logging.WARNING, "readiness check failed: database unreachable")
        return jsonify({"status": "unavailable", "database": "down"}), 503
    return jsonify({"status": "ok", "database": "up"})


# --- MEMBER AUTH ---

# Creates a new member account with a securely hashed password
@app.route("/api/users/register", methods=["POST"])
def register_user():
    data = request.get_json(silent=True) or {}
    missing = missing_fields(data, ["name", "email", "password"])
    if missing:
        return jsonify({"error": "Missing: " + ", ".join(missing)}), 400
    if len(data["password"]) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    try:
        new_user_id = execute(
            "INSERT INTO users (name, email, password, phone, address) VALUES (%s, %s, %s, %s, %s)",
            (data["name"].strip(), data["email"].strip(), generate_password_hash(data["password"]),
             data.get("phone"), data.get("address"))
        )
    except IntegrityError:
        return jsonify({"error": "That email is already registered"}), 409
    return jsonify({"message": "Member registered", "user_id": new_user_id}), 201


# Verifies email/password and returns a JWT token identifying this member
@app.route("/api/users/login", methods=["POST"])
def login_user():
    data = request.get_json(silent=True) or {}
    user = query("SELECT * FROM users WHERE email = %s", (data.get("email"),), one=True)
    if user and check_password_hash(user["password"], data.get("password") or ""):
        observability.LOGINS.labels("member", "success").inc()
        return jsonify({"message": "Login successful", "name": user["name"],
                        "token": make_token("user_id", user["user_id"], "member")})
    observability.LOGINS.labels("member", "failure").inc()
    observability.log_event(log, logging.WARNING, "login failed", event="login_failed", role="member")
    return jsonify({"error": "Invalid email or password"}), 401


# --- ADMIN AUTH ---

# Admins are seeded in the database (not self-registered) — this only logs them in
@app.route("/api/admin/login", methods=["POST"])
def login_admin():
    data = request.get_json(silent=True) or {}
    admin = query("SELECT * FROM admins WHERE email = %s", (data.get("email"),), one=True)
    if admin and check_password_hash(admin["password"], data.get("password") or ""):
        observability.LOGINS.labels("admin", "success").inc()
        return jsonify({"message": "Login successful", "name": admin["name"],
                        "token": make_token("admin_id", admin["admin_id"], "admin")})
    observability.LOGINS.labels("admin", "failure").inc()
    observability.log_event(log, logging.WARNING, "login failed", event="login_failed", role="admin")
    return jsonify({"error": "Invalid email or password"}), 401


# --- PLANS (public) ---

# Lists the plans a member can currently buy
@app.route("/api/plans", methods=["GET"])
def get_plans():
    return jsonify(query("SELECT * FROM membership_plans WHERE is_active = TRUE ORDER BY price"))


# --- MEMBER: PROFILE ---

# Identity always comes from the token, never from the URL or request body
@app.route("/api/me", methods=["GET"])
@auth_required("member")
def get_profile(payload):
    user = query("SELECT user_id, name, email, phone, address, created_at FROM users WHERE user_id = %s",
                 (payload["user_id"],), one=True)
    return jsonify(user)


# Updates name/phone/address, and optionally the password (current password required)
@app.route("/api/me", methods=["PUT"])
@auth_required("member")
def update_profile(payload):
    data = request.get_json(silent=True) or {}
    updates = {f: data[f] for f in ["name", "phone", "address"] if f in data}
    if "name" in updates and not str(updates["name"]).strip():
        return jsonify({"error": "Name cannot be empty"}), 400

    if data.get("new_password"):
        user = query("SELECT password FROM users WHERE user_id = %s", (payload["user_id"],), one=True)
        if not check_password_hash(user["password"], data.get("current_password") or ""):
            return jsonify({"error": "Current password is incorrect"}), 400
        if len(data["new_password"]) < 6:
            return jsonify({"error": "New password must be at least 6 characters"}), 400
        updates["password"] = generate_password_hash(data["new_password"])

    if not updates:
        return jsonify({"error": "No fields to update"}), 400
    update_row("users", "user_id", payload["user_id"], updates)
    return jsonify({"message": "Profile updated"})


# --- MEMBER: MEMBERSHIP & PAYMENTS ---

# Returns the member's current active membership, any pending request, and the full history
@app.route("/api/me/membership", methods=["GET"])
@auth_required("member")
def get_my_membership(payload):
    expire_memberships()
    history = query("""
        SELECT m.membership_id, m.status, m.start_date, m.end_date, m.created_at,
               DATEDIFF(m.end_date, CURDATE()) AS days_left,
               p.plan_id, p.name AS plan_name, p.price, p.duration_days
        FROM memberships m
        JOIN membership_plans p ON p.plan_id = m.plan_id
        WHERE m.user_id = %s
        ORDER BY m.membership_id DESC
    """, (payload["user_id"],))
    active = next((m for m in sorted(history, key=lambda m: m["end_date"] or datetime.date.min, reverse=True)
                   if m["status"] == "Active"), None)
    pending = next((m for m in history if m["status"] == "Pending"), None)
    latest_expired = next((m for m in history if m["status"] == "Expired"), None)
    return jsonify({"active": active, "pending": pending, "latest_expired": latest_expired, "history": history})


# Buys or renews a plan. The (simulated) payment is recorded straight away and the
# membership waits as Pending until an admin approves it.
@app.route("/api/memberships", methods=["POST"])
@auth_required("member")
def subscribe(payload):
    data = request.get_json(silent=True) or {}
    if data.get("method") not in PAYMENT_METHODS:
        return jsonify({"error": "Choose a payment method: " + ", ".join(sorted(PAYMENT_METHODS))}), 400
    plan = query("SELECT * FROM membership_plans WHERE plan_id = %s AND is_active = TRUE",
                 (data.get("plan_id"),), one=True)
    if plan is None:
        return jsonify({"error": "Plan not found"}), 404
    already = query("SELECT membership_id FROM memberships WHERE user_id = %s AND status = 'Pending'",
                    (payload["user_id"],), one=True)
    if already:
        return jsonify({"error": "You already have a request waiting for admin approval"}), 400

    # Membership + payment are saved together so one can never exist without the other
    txn_ref = "TXN" + uuid.uuid4().hex[:10].upper()
    with transaction() as cursor:
        cursor.execute("INSERT INTO memberships (user_id, plan_id) VALUES (%s, %s)",
                       (payload["user_id"], plan["plan_id"]))
        membership_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO payments (membership_id, user_id, amount, method, txn_ref) VALUES (%s, %s, %s, %s, %s)",
            (membership_id, payload["user_id"], plan["price"], data["method"], txn_ref)
        )
    observability.MEMBERSHIPS_REQUESTED.inc()
    observability.PAYMENTS.labels(data["method"]).inc()
    return jsonify({"message": "Payment successful. Waiting for admin approval.",
                    "membership_id": membership_id, "txn_ref": txn_ref}), 201


# Lists the member's own payments
@app.route("/api/me/payments", methods=["GET"])
@auth_required("member")
def get_my_payments(payload):
    return jsonify(query("""
        SELECT pay.payment_id, pay.amount, pay.method, pay.status, pay.txn_ref, pay.payment_date,
               p.name AS plan_name
        FROM payments pay
        JOIN memberships m ON m.membership_id = pay.membership_id
        JOIN membership_plans p ON p.plan_id = m.plan_id
        WHERE pay.user_id = %s
        ORDER BY pay.payment_id DESC
    """, (payload["user_id"],)))


# --- ADMIN: DASHBOARD & REPORT ---

def summary_stats():
    expire_memberships()
    return {
        "total_members": query("SELECT COUNT(*) AS n FROM users", one=True)["n"],
        "active_memberships": query(
            "SELECT COUNT(DISTINCT user_id) AS n FROM memberships WHERE status = 'Active'", one=True)["n"],
        "expired_memberships": len(query(EXPIRED_SQL)),
        "pending_approvals": query("SELECT COUNT(*) AS n FROM memberships WHERE status = 'Pending'", one=True)["n"],
        "monthly_revenue": query("""
            SELECT COALESCE(SUM(amount), 0) AS total FROM payments
            WHERE status = 'Paid' AND YEAR(payment_date) = YEAR(CURDATE())
              AND MONTH(payment_date) = MONTH(CURDATE())
        """, one=True)["total"],
    }


@app.route("/api/admin/dashboard", methods=["GET"])
@auth_required("admin")
def admin_dashboard(payload):
    return jsonify(summary_stats())


# One-page report: summary, revenue by month, plan popularity, expiring soon, member list
@app.route("/api/admin/report", methods=["GET"])
@auth_required("admin")
def admin_report(payload):
    summary = summary_stats()
    summary["total_revenue"] = query(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM payments WHERE status = 'Paid'", one=True)["total"]
    return jsonify({
        "generated_at": datetime.datetime.now(),
        "summary": summary,
        "revenue_by_month": query("""
            SELECT CONCAT(YEAR(payment_date), '-', LPAD(MONTH(payment_date), 2, '0')) AS month,
                   SUM(amount) AS revenue, COUNT(*) AS payments
            FROM payments WHERE status = 'Paid'
            GROUP BY month ORDER BY month DESC LIMIT 12
        """),
        "plan_popularity": query("""
            SELECT p.name AS plan_name, COUNT(m.membership_id) AS memberships,
                   COALESCE(SUM(pay.amount), 0) AS revenue
            FROM membership_plans p
            LEFT JOIN memberships m ON m.plan_id = p.plan_id AND m.status IN ('Active', 'Expired')
            LEFT JOIN payments pay ON pay.membership_id = m.membership_id AND pay.status = 'Paid'
            GROUP BY p.plan_id, p.name ORDER BY memberships DESC
        """),
        "expiring_soon": query("""
            SELECT u.name, u.email, u.phone, p.name AS plan_name, m.end_date,
                   DATEDIFF(m.end_date, CURDATE()) AS days_left
            FROM memberships m
            JOIN users u ON u.user_id = m.user_id
            JOIN membership_plans p ON p.plan_id = m.plan_id
            WHERE m.status = 'Active' AND m.end_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 14 DAY)
            ORDER BY m.end_date
        """),
        "members": query(MEMBER_LIST_SQL + " ORDER BY u.name"),
    })


# --- ADMIN: MEMBERS (CRUD) ---

# Lists members with their current membership status; optional ?search= matches name/email
@app.route("/api/admin/members", methods=["GET"])
@auth_required("admin")
def admin_get_members(payload):
    expire_memberships()
    search = request.args.get("search", "").strip()
    if search:
        like = f"%{search}%"
        return jsonify(query(MEMBER_LIST_SQL + " WHERE u.name LIKE %s OR u.email LIKE %s ORDER BY u.name",
                             (like, like)))
    return jsonify(query(MEMBER_LIST_SQL + " ORDER BY u.name"))


@app.route("/api/admin/members", methods=["POST"])
@auth_required("admin")
def admin_add_member(payload):
    data = request.get_json(silent=True) or {}
    missing = missing_fields(data, ["name", "email", "password"])
    if missing:
        return jsonify({"error": "Missing: " + ", ".join(missing)}), 400
    if len(data["password"]) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    try:
        new_id = execute(
            "INSERT INTO users (name, email, password, phone, address) VALUES (%s, %s, %s, %s, %s)",
            (data["name"].strip(), data["email"].strip(), generate_password_hash(data["password"]),
             data.get("phone"), data.get("address"))
        )
    except IntegrityError:
        return jsonify({"error": "That email is already registered"}), 409
    return jsonify({"message": "Member added", "user_id": new_id}), 201


@app.route("/api/admin/members/<int:user_id>", methods=["PUT"])
@auth_required("admin")
def admin_update_member(payload, user_id):
    if query("SELECT user_id FROM users WHERE user_id = %s", (user_id,), one=True) is None:
        return jsonify({"error": "Member not found"}), 404
    data = request.get_json(silent=True) or {}
    updates = {f: data[f] for f in ["name", "email", "phone", "address"] if f in data}
    if data.get("password"):
        if len(data["password"]) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400
        updates["password"] = generate_password_hash(data["password"])
    if not updates:
        return jsonify({"error": "No fields to update"}), 400
    try:
        update_row("users", "user_id", user_id, updates)
    except IntegrityError:
        return jsonify({"error": "That email is already registered"}), 409
    return jsonify({"message": "Member updated"})


# Deletes a member together with their payments and memberships
@app.route("/api/admin/members/<int:user_id>", methods=["DELETE"])
@auth_required("admin")
def admin_delete_member(payload, user_id):
    if query("SELECT user_id FROM users WHERE user_id = %s", (user_id,), one=True) is None:
        return jsonify({"error": "Member not found"}), 404
    with transaction() as cursor:
        cursor.execute("DELETE FROM payments WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM memberships WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
    return jsonify({"message": "Member deleted"})


# --- ADMIN: MEMBERSHIPS (approval) ---

# Lists memberships, optionally filtered by ?status=Pending|Active|Expired|Rejected
@app.route("/api/admin/memberships", methods=["GET"])
@auth_required("admin")
def admin_get_memberships(payload):
    expire_memberships()
    sql = """
        SELECT m.membership_id, m.status, m.start_date, m.end_date, m.created_at,
               u.name AS user_name, u.email, p.name AS plan_name, p.price
        FROM memberships m
        JOIN users u ON u.user_id = m.user_id
        JOIN membership_plans p ON p.plan_id = m.plan_id
    """
    status = request.args.get("status")
    if status:
        return jsonify(query(sql + " WHERE m.status = %s ORDER BY m.membership_id DESC", (status,)))
    return jsonify(query(sql + " ORDER BY m.membership_id DESC"))


# Approves (starts the membership) or rejects (refunds the payment) a Pending membership
@app.route("/api/admin/memberships/<int:membership_id>", methods=["PUT"])
@auth_required("admin")
def admin_decide_membership(payload, membership_id):
    data = request.get_json(silent=True) or {}
    decision = data.get("status")
    if decision not in ("Approved", "Rejected"):
        return jsonify({"error": "status must be Approved or Rejected"}), 400
    membership = query("""
        SELECT m.membership_id, m.user_id, m.status, p.duration_days
        FROM memberships m JOIN membership_plans p ON p.plan_id = m.plan_id
        WHERE m.membership_id = %s
    """, (membership_id,), one=True)
    if membership is None:
        return jsonify({"error": "Membership not found"}), 404
    if membership["status"] != "Pending":
        return jsonify({"error": "Only pending memberships can be approved or rejected"}), 400

    if decision == "Approved":
        # A renewal starts the day after the member's current membership ends, so no paid days are lost
        start = datetime.date.today()
        current = query("SELECT MAX(end_date) AS current_end FROM memberships WHERE user_id = %s AND status = 'Active'",
                        (membership["user_id"],), one=True)
        current_end = current["current_end"] if current else None
        if current_end and current_end >= start:
            start = current_end + datetime.timedelta(days=1)
        end = start + datetime.timedelta(days=membership["duration_days"])
        execute("UPDATE memberships SET status = 'Active', start_date = %s, end_date = %s WHERE membership_id = %s",
                (start, end, membership_id))
    else:
        with transaction() as cursor:
            cursor.execute("UPDATE memberships SET status = 'Rejected' WHERE membership_id = %s", (membership_id,))
            cursor.execute("UPDATE payments SET status = 'Refunded' WHERE membership_id = %s", (membership_id,))
    observability.DECISIONS.labels(decision.lower()).inc()
    return jsonify({"message": f"Membership {decision.lower()}"})


@app.route("/api/admin/expired", methods=["GET"])
@auth_required("admin")
def admin_get_expired(payload):
    expire_memberships()
    return jsonify(query(EXPIRED_SQL))


# --- ADMIN: PLANS (CRUD) ---

@app.route("/api/admin/plans", methods=["GET"])
@auth_required("admin")
def admin_get_plans(payload):
    return jsonify(query("SELECT * FROM membership_plans ORDER BY price"))


def validate_plan(data, partial=False):
    if not partial:
        missing = missing_fields(data, ["name", "duration_days", "price"])
        if missing:
            return "Missing: " + ", ".join(missing)
    try:
        if "duration_days" in data and int(data["duration_days"]) <= 0:
            return "Duration must be at least 1 day"
        if "price" in data and float(data["price"]) < 0:
            return "Price cannot be negative"
    except (TypeError, ValueError):
        return "Duration and price must be numbers"
    return None


@app.route("/api/admin/plans", methods=["POST"])
@auth_required("admin")
def admin_add_plan(payload):
    data = request.get_json(silent=True) or {}
    error = validate_plan(data)
    if error:
        return jsonify({"error": error}), 400
    new_id = execute(
        "INSERT INTO membership_plans (name, duration_days, price, description) VALUES (%s, %s, %s, %s)",
        (data["name"].strip(), int(data["duration_days"]), data["price"], data.get("description"))
    )
    return jsonify({"message": "Plan added", "plan_id": new_id}), 201


@app.route("/api/admin/plans/<int:plan_id>", methods=["PUT"])
@auth_required("admin")
def admin_update_plan(payload, plan_id):
    if query("SELECT plan_id FROM membership_plans WHERE plan_id = %s", (plan_id,), one=True) is None:
        return jsonify({"error": "Plan not found"}), 404
    data = request.get_json(silent=True) or {}
    error = validate_plan(data, partial=True)
    if error:
        return jsonify({"error": error}), 400
    updates = {f: data[f] for f in ["name", "duration_days", "price", "description", "is_active"] if f in data}
    if not updates:
        return jsonify({"error": "No fields to update"}), 400
    update_row("membership_plans", "plan_id", plan_id, updates)
    return jsonify({"message": "Plan updated"})


# A plan that memberships already reference can't be deleted (that would erase history) — deactivate it instead
@app.route("/api/admin/plans/<int:plan_id>", methods=["DELETE"])
@auth_required("admin")
def admin_delete_plan(payload, plan_id):
    if query("SELECT plan_id FROM membership_plans WHERE plan_id = %s", (plan_id,), one=True) is None:
        return jsonify({"error": "Plan not found"}), 404
    if query("SELECT membership_id FROM memberships WHERE plan_id = %s LIMIT 1", (plan_id,), one=True):
        return jsonify({"error": "This plan has memberships — deactivate it instead of deleting"}), 400
    execute("DELETE FROM membership_plans WHERE plan_id = %s", (plan_id,))
    return jsonify({"message": "Plan deleted"})


# Local development only; containers run the app with gunicorn. Binding all interfaces is intended:
# inside a container the published port is only reachable through Docker anyway.
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")  # nosec B104
