"""Login, registration, token checks and the member's own profile."""
import datetime

import jwt
import pytest
from mysql.connector import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

import app as app_module
import observability


def logins(role, result):
    return observability.LOGINS.labels(role, result)._value.get()


# ---------- token checks ----------

def test_missing_token_is_401(client):
    response = client.get("/api/me")
    assert response.status_code == 401
    assert response.get_json()["error"] == "Token is missing"


@pytest.mark.parametrize("header", ["Bearer nonsense", "Bearer", "garbage"])
def test_bad_token_is_401(client, header):
    assert client.get("/api/me", headers={"Authorization": header}).status_code == 401


def test_expired_token_is_401(client):
    expired = jwt.encode({"user_id": 7, "role": "member",
                          "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)},
                         app_module.app.config["SECRET_KEY"], algorithm="HS256")
    assert client.get("/api/me", headers={"Authorization": "Bearer " + expired}).status_code == 401


def test_token_signed_with_another_key_is_rejected(client):
    forged = jwt.encode({"user_id": 7, "role": "member"}, "some-other-key-that-is-long-enough-xx", algorithm="HS256")
    assert client.get("/api/me", headers={"Authorization": "Bearer " + forged}).status_code == 401


def test_member_token_cannot_call_admin_api(client, member_headers):
    response = client.get("/api/admin/dashboard", headers=member_headers)
    assert response.status_code == 403
    assert response.get_json()["error"] == "Admins only"


def test_admin_token_cannot_call_member_api(client, admin_headers):
    response = client.get("/api/me", headers=admin_headers)
    assert response.status_code == 403
    assert response.get_json()["error"] == "Members only"


# ---------- registration ----------

def test_register_creates_member_with_hashed_password(client, db):
    response = client.post("/api/users/register", json={
        "name": "  Asha Rao ", "email": " asha@example.com ", "password": "secret1", "phone": "99"})
    assert response.status_code == 201
    assert response.get_json()["user_id"] == 101
    _, sql, params = db.statements("execute", "INSERT INTO users")[0]
    assert params[0] == "Asha Rao" and params[1] == "asha@example.com"
    assert params[2] != "secret1"                      # never stored in plain text
    assert check_password_hash(params[2], "secret1")


@pytest.mark.parametrize("body", [
    {}, {"name": "A"}, {"name": "A", "email": "a@x.com"}, {"name": "  ", "email": "a@x.com", "password": "secret1"},
])
def test_register_requires_name_email_password(client, body):
    response = client.post("/api/users/register", json=body)
    assert response.status_code == 400
    assert response.get_json()["error"].startswith("Missing")


def test_register_rejects_short_password(client):
    response = client.post("/api/users/register", json={"name": "A", "email": "a@x.com", "password": "abc"})
    assert response.status_code == 400


def test_register_duplicate_email_is_409(client, db):
    db.fail_on("INSERT INTO users", IntegrityError("duplicate"))
    response = client.post("/api/users/register", json={"name": "A", "email": "a@x.com", "password": "secret1"})
    assert response.status_code == 409


# ---------- login ----------

def test_member_login_returns_token_for_that_member(client, db):
    db.when("FROM users WHERE email", [{"user_id": 7, "name": "Asha", "password": generate_password_hash("secret1")}])
    before = logins("member", "success")
    response = client.post("/api/users/login", json={"email": "asha@example.com", "password": "secret1"})
    assert response.status_code == 200
    payload = jwt.decode(response.get_json()["token"], app_module.app.config["SECRET_KEY"], algorithms=["HS256"])
    assert payload["user_id"] == 7 and payload["role"] == "member"
    assert logins("member", "success") == before + 1


def test_member_login_wrong_password_is_401_and_counted(client, db):
    db.when("FROM users WHERE email", [{"user_id": 7, "name": "Asha", "password": generate_password_hash("secret1")}])
    before = logins("member", "failure")
    response = client.post("/api/users/login", json={"email": "asha@example.com", "password": "wrong"})
    assert response.status_code == 401
    assert logins("member", "failure") == before + 1


@pytest.mark.parametrize("body", [{"email": "nobody@example.com", "password": "x"}, {}])
def test_member_login_unknown_user_is_401(client, body):
    assert client.post("/api/users/login", json=body).status_code == 401


def test_admin_login_returns_admin_token(client, db):
    db.when("FROM admins WHERE email", [{"admin_id": 1, "name": "Gym Admin", "password": generate_password_hash("Admin@1")}])
    response = client.post("/api/admin/login", json={"email": "admin@gym.com", "password": "Admin@1"})
    assert response.status_code == 200
    payload = jwt.decode(response.get_json()["token"], app_module.app.config["SECRET_KEY"], algorithms=["HS256"])
    assert payload["admin_id"] == 1 and payload["role"] == "admin"


def test_admin_login_failure_is_401(client, db):
    db.when("FROM admins WHERE email", [{"admin_id": 1, "name": "Gym Admin", "password": generate_password_hash("Admin@1")}])
    assert client.post("/api/admin/login", json={"email": "admin@gym.com", "password": "nope"}).status_code == 401
    assert client.post("/api/admin/login", json={"email": "other@gym.com", "password": "nope"}).status_code == 401


# ---------- profile ----------

def test_get_profile_uses_identity_from_token(client, db, member_headers):
    db.when("FROM users WHERE user_id", [{"user_id": 7, "name": "Asha", "email": "asha@example.com",
                                          "phone": None, "address": None,
                                          "created_at": datetime.datetime(2026, 9, 20, 10, 0)}])
    response = client.get("/api/me", headers=member_headers)
    assert response.status_code == 200
    assert response.get_json()["created_at"] == "2026-09-20T10:00:00"
    assert db.statements("query", "FROM users WHERE user_id")[0][2] == (7,)   # id came from the token


def test_update_profile_changes_only_allowed_fields(client, db, member_headers):
    response = client.put("/api/me", headers=member_headers,
                          json={"name": "Asha K", "phone": "123", "email": "hacker@example.com", "role": "admin"})
    assert response.status_code == 200
    _, table, key, value, updates = db.statements("update_row")[0]
    assert (table, key, value) == ("users", "user_id", 7)
    assert updates == {"name": "Asha K", "phone": "123"}      # email and role were ignored


def test_update_profile_rejects_blank_name_and_empty_body(client, member_headers):
    assert client.put("/api/me", headers=member_headers, json={"name": "  "}).status_code == 400
    assert client.put("/api/me", headers=member_headers, json={}).status_code == 400


def test_change_password_needs_correct_current_password(client, db, member_headers):
    db.when("SELECT password FROM users", [{"password": generate_password_hash("oldpass1")}])
    wrong = client.put("/api/me", headers=member_headers, json={"new_password": "newpass1", "current_password": "x"})
    assert wrong.status_code == 400
    short = client.put("/api/me", headers=member_headers, json={"new_password": "abc", "current_password": "oldpass1"})
    assert short.status_code == 400
    ok = client.put("/api/me", headers=member_headers, json={"new_password": "newpass1", "current_password": "oldpass1"})
    assert ok.status_code == 200
    stored = db.statements("update_row")[0][4]["password"]
    assert check_password_hash(stored, "newpass1")
