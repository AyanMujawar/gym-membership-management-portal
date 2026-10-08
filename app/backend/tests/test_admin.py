"""Admin features: dashboard and report, member CRUD, membership lists, plan CRUD."""
import datetime
from decimal import Decimal

import pytest
from mysql.connector import IntegrityError
from werkzeug.security import check_password_hash

PLAN_ROW = {"plan_id": 3, "name": "Yearly", "duration_days": 365, "price": Decimal("9000.00"), "is_active": 1}


@pytest.fixture
def dashboard_data(db):
    db.when("COUNT\\(\\*\\) AS n FROM users", [{"n": 12}])
    db.when("COUNT\\(DISTINCT user_id\\)", [{"n": 8}])
    db.when("WHERE m.status = 'Expired'", [{"name": "Rahul"}, {"name": "Meena"}])
    db.when("COUNT\\(\\*\\) AS n FROM memberships WHERE status = 'Pending'", [{"n": 3}])
    db.when("FROM payments\\s+WHERE status = 'Paid' AND YEAR", [{"total": Decimal("15700.50")}])
    db.when("FROM payments WHERE status = 'Paid'$", [{"total": Decimal("99000")}])


# ---------- dashboard and report ----------

def test_dashboard_numbers(client, admin_headers, dashboard_data):
    body = client.get("/api/admin/dashboard", headers=admin_headers).get_json()
    assert body == {"total_members": 12, "active_memberships": 8, "expired_memberships": 2,
                    "pending_approvals": 3, "monthly_revenue": 15700.5}


def test_dashboard_expires_overdue_memberships_first(client, db, admin_headers, dashboard_data):
    client.get("/api/admin/dashboard", headers=admin_headers)
    assert db.statements("execute", "SET status = 'Expired'")


def test_report_has_every_section(client, db, admin_headers, dashboard_data):
    db.when("GROUP BY month", [{"month": "2026-09", "revenue": Decimal("15700.50"), "payments": 6}])
    db.when("GROUP BY p.plan_id", [{"plan_name": "Monthly", "memberships": 5, "revenue": Decimal("5000")}])
    db.when("BETWEEN CURDATE\\(\\)", [{"name": "Asha", "days_left": 4}])
    db.when("ORDER BY u.name", [{"name": "Asha"}, {"name": "Rahul"}])
    body = client.get("/api/admin/report", headers=admin_headers).get_json()
    assert set(body) == {"generated_at", "summary", "revenue_by_month", "plan_popularity", "expiring_soon", "members"}
    assert body["summary"]["total_revenue"] == 99000
    assert body["revenue_by_month"][0]["revenue"] == 15700.5
    assert len(body["members"]) == 2


def test_dashboard_and_report_are_admin_only(client, member_headers):
    assert client.get("/api/admin/dashboard", headers=member_headers).status_code == 403
    assert client.get("/api/admin/report", headers=member_headers).status_code == 403


# ---------- members ----------

def test_list_members_with_and_without_search(client, db, admin_headers):
    db.when("ORDER BY u.name", [{"name": "Asha"}])
    assert client.get("/api/admin/members", headers=admin_headers).status_code == 200
    client.get("/api/admin/members?search=%20ash%20", headers=admin_headers)
    searched = db.statements("query", "WHERE u.name LIKE")[0]
    assert searched[2] == ("%ash%", "%ash%")


def test_admin_adds_member_with_hashed_password(client, db, admin_headers):
    response = client.post("/api/admin/members", headers=admin_headers,
                           json={"name": "Walk In", "email": "walk@in.com", "password": "walkin1"})
    assert response.status_code == 201
    assert check_password_hash(db.statements("execute", "INSERT INTO users")[0][2][2], "walkin1")


@pytest.mark.parametrize("body,status", [
    ({"name": "A", "email": "a@x.com"}, 400),
    ({"name": "A", "email": "a@x.com", "password": "abc"}, 400),
])
def test_admin_add_member_validation(client, admin_headers, body, status):
    assert client.post("/api/admin/members", headers=admin_headers, json=body).status_code == status


def test_admin_add_member_duplicate_email(client, db, admin_headers):
    db.fail_on("INSERT INTO users", IntegrityError("duplicate"))
    body = {"name": "A", "email": "a@x.com", "password": "secret1"}
    assert client.post("/api/admin/members", headers=admin_headers, json=body).status_code == 409


def test_update_unknown_member_is_404(client, admin_headers):
    assert client.put("/api/admin/members/9", headers=admin_headers, json={"phone": "1"}).status_code == 404


def test_update_member(client, db, admin_headers):
    db.when("SELECT user_id FROM users WHERE user_id", [{"user_id": 9}])
    response = client.put("/api/admin/members/9", headers=admin_headers,
                          json={"phone": "555", "password": "brandnew1", "is_admin": True})
    assert response.status_code == 200
    updates = db.statements("update_row")[0][4]
    assert set(updates) == {"phone", "password"}                     # unknown fields are ignored
    assert check_password_hash(updates["password"], "brandnew1")


def test_update_member_validation_and_duplicates(client, db, admin_headers):
    db.when("SELECT user_id FROM users WHERE user_id", [{"user_id": 9}])
    assert client.put("/api/admin/members/9", headers=admin_headers, json={}).status_code == 400
    assert client.put("/api/admin/members/9", headers=admin_headers, json={"password": "abc"}).status_code == 400
    db.fail_on("UPDATE users", IntegrityError("duplicate"))
    assert client.put("/api/admin/members/9", headers=admin_headers, json={"email": "x@y.com"}).status_code == 409


def test_delete_member_removes_payments_memberships_then_user(client, db, admin_headers):
    db.when("SELECT user_id FROM users WHERE user_id", [{"user_id": 9}])
    assert client.delete("/api/admin/members/9", headers=admin_headers).status_code == 200
    tables = [c[1].split("FROM ")[1].split(" ")[0] for c in db.statements("transaction")]
    assert tables == ["payments", "memberships", "users"]            # children first, so no orphans


def test_delete_unknown_member_is_404(client, admin_headers):
    assert client.delete("/api/admin/members/9", headers=admin_headers).status_code == 404


# ---------- membership lists ----------

def test_list_memberships_filtered_by_status(client, db, admin_headers):
    db.when("FROM memberships m\\s+JOIN users u", [{"membership_id": 1, "status": "Pending"}])
    assert client.get("/api/admin/memberships", headers=admin_headers).status_code == 200
    client.get("/api/admin/memberships?status=Pending", headers=admin_headers)
    assert db.statements("query", "WHERE m.status = %s")[0][2] == ("Pending",)


def test_expired_list(client, db, admin_headers):
    db.when("DATEDIFF\\(CURDATE\\(\\), m.end_date\\)", [{"name": "Rahul", "end_date": datetime.date(2026, 9, 5)}])
    body = client.get("/api/admin/expired", headers=admin_headers).get_json()
    assert body == [{"name": "Rahul", "end_date": "2026-09-05"}]


# ---------- plans ----------

def test_public_plans_list_only_active_plans(client, db):
    db.when("FROM membership_plans WHERE is_active", [PLAN_ROW])
    body = client.get("/api/plans").get_json()
    assert body[0]["price"] == 9000.0                  # Decimal comes out as a plain number
    assert db.statements("query", "is_active = TRUE")


def test_admin_plans_list_includes_hidden_plans(client, db, admin_headers):
    db.when("FROM membership_plans ORDER BY price", [PLAN_ROW, dict(PLAN_ROW, plan_id=4, is_active=0)])
    assert len(client.get("/api/admin/plans", headers=admin_headers).get_json()) == 2


def test_add_plan(client, db, admin_headers):
    response = client.post("/api/admin/plans", headers=admin_headers,
                           json={"name": " Weekly ", "duration_days": "7", "price": 250, "description": "1 week"})
    assert response.status_code == 201
    assert db.statements("execute", "INSERT INTO membership_plans")[0][2] == ("Weekly", 7, 250, "1 week")


@pytest.mark.parametrize("body", [
    {"duration_days": 7, "price": 1},                              # no name
    {"name": "X", "duration_days": 0, "price": 1},                 # zero days
    {"name": "X", "duration_days": 7, "price": -5},                # negative price
    {"name": "X", "duration_days": "many", "price": 1},            # not a number
])
def test_add_plan_validation(client, admin_headers, body):
    assert client.post("/api/admin/plans", headers=admin_headers, json=body).status_code == 400


def test_update_plan(client, db, admin_headers):
    db.when("SELECT plan_id FROM membership_plans WHERE plan_id", [{"plan_id": 3}])
    response = client.put("/api/admin/plans/3", headers=admin_headers, json={"price": 8500, "is_active": False})
    assert response.status_code == 200
    assert db.statements("update_row")[0][1:] == ("membership_plans", "plan_id", 3, {"price": 8500, "is_active": False})


def test_update_plan_errors(client, db, admin_headers):
    assert client.put("/api/admin/plans/3", headers=admin_headers, json={"price": 1}).status_code == 404
    db.when("SELECT plan_id FROM membership_plans WHERE plan_id", [{"plan_id": 3}])
    assert client.put("/api/admin/plans/3", headers=admin_headers, json={"price": -1}).status_code == 400
    assert client.put("/api/admin/plans/3", headers=admin_headers, json={}).status_code == 400


def test_plan_in_use_cannot_be_deleted(client, db, admin_headers):
    db.when("SELECT plan_id FROM membership_plans WHERE plan_id", [{"plan_id": 3}])
    db.when("SELECT membership_id FROM memberships WHERE plan_id", [{"membership_id": 1}])
    assert client.delete("/api/admin/plans/3", headers=admin_headers).status_code == 400
    assert not db.statements("execute", "DELETE FROM membership_plans")


def test_unused_plan_can_be_deleted_and_unknown_is_404(client, db, admin_headers):
    assert client.delete("/api/admin/plans/3", headers=admin_headers).status_code == 404
    db.when("SELECT plan_id FROM membership_plans WHERE plan_id", [{"plan_id": 3}])
    assert client.delete("/api/admin/plans/3", headers=admin_headers).status_code == 200
    assert db.statements("execute", "DELETE FROM membership_plans")
