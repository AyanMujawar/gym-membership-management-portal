"""Health probes, metrics, error handling, configuration safety, logging and the db module."""
import json
import logging

import pytest

import app as app_module
import db as db_module
import observability


# ---------- health ----------

@pytest.mark.parametrize("path", ["/api/health", "/api/health/live"])
def test_liveness_never_touches_the_database(client, db, path):
    response = client.get(path)
    assert response.status_code == 200 and response.get_json()["status"] == "ok"
    assert not db.calls


def test_readiness_ok_when_database_answers(client, db):
    db.when("SELECT 1", [{"ok": 1}])
    response = client.get("/api/health/ready")
    assert response.status_code == 200 and response.get_json()["database"] == "up"


def test_readiness_is_503_when_database_is_down(client, db):
    db.fail_on("SELECT 1", RuntimeError("connection refused"))
    response = client.get("/api/health/ready")
    assert response.status_code == 503 and response.get_json()["database"] == "down"
    assert client.get("/api/health/live").status_code == 200    # the process itself is still fine


# ---------- metrics ----------

def test_metrics_label_requests_by_route_template_not_real_url(client, admin_headers):
    client.get("/api/admin/members/5", headers=admin_headers)   # 404 member, but still a counted request
    text = client.get("/metrics").get_data(as_text=True)
    assert "http_requests_total" in text and "http_request_duration_seconds_bucket" in text
    assert 'endpoint="/api/admin/members/<int:user_id>"' in text
    assert "/api/admin/members/5" not in text                   # real ids would explode the series count


def test_metrics_include_business_counters(client):
    text = client.get("/metrics").get_data(as_text=True)
    for name in ("gym_logins_total", "gym_memberships_requested_total", "gym_payments_total",
                 "gym_membership_decisions_total"):
        assert name in text


# ---------- errors always come back as JSON ----------

def test_unknown_route_is_json_404(client):
    response = client.get("/api/nothing-here")
    assert response.status_code == 404 and "error" in response.get_json()


def test_wrong_method_is_json_405(client):
    response = client.delete("/api/plans")
    assert response.status_code == 405 and "error" in response.get_json()


def test_unexpected_failure_is_json_500_and_not_leaked(client, db):
    db.fail_on("FROM membership_plans WHERE is_active", RuntimeError("secret internal detail"))
    response = client.get("/api/plans")
    assert response.status_code == 500
    assert response.get_json() == {"error": "Internal server error"}


def test_server_errors_are_counted_for_the_error_rate_alert(client, db):
    db.fail_on("FROM membership_plans WHERE is_active", RuntimeError("boom"))
    client.get("/api/plans")
    text = client.get("/metrics").get_data(as_text=True)
    assert 'http_requests_total{endpoint="/api/plans",method="GET",status="500"}' in text


# ---------- production safety ----------

def test_development_falls_back_to_a_default_key():
    assert app_module.load_secret_key({}) == "dev-secret-key-change-in-production"
    assert app_module.load_secret_key({"SECRET_KEY": "mine"}) == "mine"


@pytest.mark.parametrize("key", ["", "change-this-secret-key", "dev-secret-key-change-in-production", "too-short"])
def test_production_refuses_missing_default_or_weak_keys(key):
    with pytest.raises(RuntimeError):
        app_module.load_secret_key({"APP_ENV": "production", "SECRET_KEY": key})


def test_production_accepts_a_long_random_key():
    key = "x" * 40
    assert app_module.load_secret_key({"APP_ENV": "production", "SECRET_KEY": key}) == key


# ---------- logging ----------

def make_record(msg="hello", exc_info=None, **fields):
    record = logging.LogRecord("gym.test", logging.WARNING, __file__, 1, msg, None, exc_info)
    record.fields = fields
    return record


def test_log_lines_are_json_with_extra_fields():
    line = json.loads(observability.JsonFormatter().format(make_record("login failed", role="admin")))
    assert line["msg"] == "login failed" and line["level"] == "WARNING" and line["role"] == "admin"
    assert line["ts"].endswith("+00:00")


def test_log_lines_include_exceptions():
    try:
        raise ValueError("bad")
    except ValueError:
        import sys
        line = json.loads(observability.JsonFormatter().format(make_record(exc_info=sys.exc_info())))
    assert "ValueError: bad" in line["exception"]


def test_log_event_attaches_fields(caplog):
    with caplog.at_level(logging.INFO, logger="gym.test"):
        observability.log_event(logging.getLogger("gym.test"), logging.INFO, "something", event="x", count=2)
    assert caplog.records[0].fields == {"event": "x", "count": 2}


# ---------- the real db module, against a fake connection ----------

class FakeDbCursor:
    def __init__(self, conn, dictionary=False):
        self.conn, self.dictionary, self.lastrowid, self.closed = conn, dictionary, 42, False

    def execute(self, sql, params=()):
        if "boom" in sql:
            raise RuntimeError("sql failed")
        self.conn.executed.append((sql, params))

    def fetchone(self):
        return {"n": 1}

    def fetchall(self):
        return [{"n": 1}, {"n": 2}]

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self):
        self.executed, self.committed, self.rolled_back, self.closed = [], False, False, False

    def cursor(self, dictionary=False):
        return FakeDbCursor(self, dictionary)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.fixture
def conn(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(db_module, "get_db_connection", lambda: connection)
    return connection


def test_connection_settings_come_from_the_environment(monkeypatch):
    seen = {}
    monkeypatch.setattr(db_module.mysql.connector, "connect", lambda **kw: seen.update(kw) or "connection")
    monkeypatch.setenv("DB_HOST", "db")
    monkeypatch.setenv("DB_PASSWORD", "s3cret")
    assert db_module.get_db_connection() == "connection"
    assert seen["host"] == "db" and seen["password"] == "s3cret" and seen["database"] == "gym_portal"


def test_query_returns_rows_and_always_closes(conn):
    assert db_module.query("SELECT 1") == [{"n": 1}, {"n": 2}]
    assert db_module.query("SELECT 1", one=True) == {"n": 1}
    assert conn.closed
    with pytest.raises(RuntimeError):
        db_module.query("SELECT boom")
    assert conn.closed


def test_execute_commits_and_returns_new_id(conn):
    assert db_module.execute("INSERT INTO t VALUES (1)") == 42
    assert conn.committed and conn.closed


def test_transaction_commits_on_success(conn):
    with db_module.transaction() as cursor:
        cursor.execute("INSERT 1")
        cursor.execute("INSERT 2")
    assert conn.committed and not conn.rolled_back and conn.closed
    assert len(conn.executed) == 2


def test_transaction_rolls_back_when_anything_fails(conn):
    with pytest.raises(RuntimeError):
        with db_module.transaction() as cursor:
            cursor.execute("INSERT 1")
            cursor.execute("boom")
    assert conn.rolled_back and not conn.committed and conn.closed


def test_update_row_builds_parameterised_sql(conn):
    db_module.update_row("users", "user_id", 7, {"name": "A", "phone": "1"})
    assert conn.executed == [("UPDATE users SET name = %s, phone = %s WHERE user_id = %s", ("A", "1", 7))]


@pytest.mark.parametrize("table,key,updates", [
    ("users; DROP TABLE users", "user_id", {"name": "A"}),
    ("users", "user_id", {"name = 'x', admin": "A"}),
    ("users", "1=1 --", {"name": "A"}),
])
def test_update_row_rejects_unsafe_identifiers(conn, table, key, updates):
    with pytest.raises(ValueError):
        db_module.update_row(table, key, 7, updates)
    assert not conn.executed
