"""The member's membership life cycle: view, buy or renew, pay, and the admin's decision."""
import datetime
from decimal import Decimal

import pytest

import observability

TODAY = datetime.date.today()
PLAN = {"plan_id": 2, "name": "Quarterly", "duration_days": 90, "price": Decimal("2700.00"), "is_active": 1}
PENDING_ROW = {"membership_id": 5, "user_id": 7, "status": "Pending", "duration_days": 30}


def counter(metric, *labels):
    return (metric.labels(*labels) if labels else metric)._value.get()


# ---------- viewing the membership ----------

def test_my_membership_picks_active_pending_and_latest_expired(client, db, member_headers):
    db.when("FROM memberships m\\s+JOIN membership_plans p ON p.plan_id = m.plan_id\\s+WHERE m.user_id", [
        {"membership_id": 4, "status": "Pending", "end_date": None, "days_left": None, "plan_name": "Monthly"},
        {"membership_id": 3, "status": "Active", "end_date": TODAY + datetime.timedelta(days=100),
         "days_left": 100, "plan_name": "Quarterly"},
        {"membership_id": 2, "status": "Active", "end_date": TODAY + datetime.timedelta(days=10),
         "days_left": 10, "plan_name": "Monthly"},
        {"membership_id": 1, "status": "Expired", "end_date": TODAY - datetime.timedelta(days=30),
         "days_left": -30, "plan_name": "Monthly"},
    ])
    body = client.get("/api/me/membership", headers=member_headers).get_json()
    assert body["active"]["membership_id"] == 3          # the Active one that ends last
    assert body["pending"]["membership_id"] == 4
    assert body["latest_expired"]["membership_id"] == 1
    assert len(body["history"]) == 4


def test_my_membership_with_no_history(client, member_headers):
    body = client.get("/api/me/membership", headers=member_headers).get_json()
    assert body == {"active": None, "pending": None, "latest_expired": None, "history": []}


def test_reading_membership_first_expires_overdue_ones(client, db, member_headers):
    client.get("/api/me/membership", headers=member_headers)
    assert db.statements("execute", "SET status = 'Expired'")


def test_my_payments_lists_only_this_members_payments(client, db, member_headers):
    db.when("FROM payments pay", [{"payment_id": 1, "amount": Decimal("1000.00"), "method": "UPI"}])
    response = client.get("/api/me/payments", headers=member_headers)
    assert response.get_json()[0]["amount"] == 1000.0
    assert db.statements("query", "FROM payments pay")[0][2] == (7,)


# ---------- buying / renewing ----------

def test_subscribe_creates_membership_and_payment_together(client, db, member_headers):
    db.when("FROM membership_plans WHERE plan_id", [PLAN])
    before_requested = counter(observability.MEMBERSHIPS_REQUESTED)
    before_upi = counter(observability.PAYMENTS, "UPI")
    response = client.post("/api/memberships", headers=member_headers, json={"plan_id": 2, "method": "UPI"})
    assert response.status_code == 201
    body = response.get_json()
    assert body["txn_ref"].startswith("TXN") and len(body["txn_ref"]) == 13
    inserts = db.statements("transaction")
    assert [c[1].split("(")[0].strip() for c in inserts] == ["INSERT INTO memberships", "INSERT INTO payments"]
    membership_params, payment_params = inserts[0][2], inserts[1][2]
    assert membership_params == (7, 2)                      # the member comes from the token
    assert payment_params[0] == body["membership_id"] and payment_params[2] == Decimal("2700.00")
    assert counter(observability.MEMBERSHIPS_REQUESTED) == before_requested + 1
    assert counter(observability.PAYMENTS, "UPI") == before_upi + 1


@pytest.mark.parametrize("body", [{"plan_id": 2}, {"plan_id": 2, "method": "Bitcoin"}, {}])
def test_subscribe_needs_a_valid_payment_method(client, member_headers, body):
    assert client.post("/api/memberships", headers=member_headers, json=body).status_code == 400


def test_subscribe_unknown_plan_is_404(client, member_headers):
    response = client.post("/api/memberships", headers=member_headers, json={"plan_id": 99, "method": "UPI"})
    assert response.status_code == 404


def test_only_one_pending_request_at_a_time(client, db, member_headers):
    db.when("FROM membership_plans WHERE plan_id", [PLAN])
    db.when("FROM memberships WHERE user_id = %s AND status = 'Pending'", [{"membership_id": 5}])
    response = client.post("/api/memberships", headers=member_headers, json={"plan_id": 2, "method": "Card"})
    assert response.status_code == 400
    assert not db.statements("transaction")                 # nothing was written


def test_subscribe_requires_member_login(client):
    assert client.post("/api/memberships", json={"plan_id": 2, "method": "UPI"}).status_code == 401


# ---------- admin decisions ----------

@pytest.fixture
def pending(db):
    db.when("FROM memberships m JOIN membership_plans p", [PENDING_ROW])
    db.when("SELECT MAX\\(end_date\\)", [{"current_end": None}])


def test_decision_must_be_approved_or_rejected(client, admin_headers):
    response = client.put("/api/admin/memberships/5", headers=admin_headers, json={"status": "Maybe"})
    assert response.status_code == 400


def test_decision_on_unknown_membership_is_404(client, admin_headers):
    assert client.put("/api/admin/memberships/5", headers=admin_headers, json={"status": "Approved"}).status_code == 404


def test_only_pending_memberships_can_be_decided(client, db, admin_headers):
    db.when("FROM memberships m JOIN membership_plans p", [dict(PENDING_ROW, status="Active")])
    assert client.put("/api/admin/memberships/5", headers=admin_headers, json={"status": "Approved"}).status_code == 400


def test_member_cannot_approve_their_own_membership(client, member_headers):
    assert client.put("/api/admin/memberships/5", headers=member_headers, json={"status": "Approved"}).status_code == 403


def test_approval_starts_membership_today(client, db, admin_headers, pending):
    before = counter(observability.DECISIONS, "approved")
    response = client.put("/api/admin/memberships/5", headers=admin_headers, json={"status": "Approved"})
    assert response.status_code == 200
    _, sql, params = db.statements("execute", "SET status = 'Active'")[0]
    assert params == (TODAY, TODAY + datetime.timedelta(days=30), 5)
    assert counter(observability.DECISIONS, "approved") == before + 1


def test_renewal_starts_the_day_after_the_current_membership_ends(client, db, admin_headers, pending):
    db.when("SELECT MAX\\(end_date\\)", [{"current_end": TODAY + datetime.timedelta(days=10)}])
    client.put("/api/admin/memberships/5", headers=admin_headers, json={"status": "Approved"})
    start = TODAY + datetime.timedelta(days=11)
    assert db.statements("execute", "SET status = 'Active'")[0][2] == (start, start + datetime.timedelta(days=30), 5)


def test_renewal_after_a_lapsed_membership_starts_today(client, db, admin_headers, pending):
    db.when("SELECT MAX\\(end_date\\)", [{"current_end": TODAY - datetime.timedelta(days=3)}])
    client.put("/api/admin/memberships/5", headers=admin_headers, json={"status": "Approved"})
    assert db.statements("execute", "SET status = 'Active'")[0][2][0] == TODAY


def test_rejection_refunds_the_payment_in_the_same_transaction(client, db, admin_headers, pending):
    response = client.put("/api/admin/memberships/5", headers=admin_headers, json={"status": "Rejected"})
    assert response.status_code == 200
    sqls = [c[1] for c in db.statements("transaction")]
    assert "SET status = 'Rejected'" in sqls[0] and "SET status = 'Refunded'" in sqls[1]
    assert not db.statements("execute", "SET status = 'Active'")
