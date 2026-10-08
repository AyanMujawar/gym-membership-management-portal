"""Shared test setup: a fake database layer, so tests never need MySQL (or Docker) and run in seconds."""
import re
from contextlib import contextmanager

import pytest

import app as app_module


class FakeCursor:
    """Stands in for the cursor handed out by db.transaction()."""

    def __init__(self, db):
        self.db = db
        self.lastrowid = None

    def execute(self, sql, params=()):
        self.db.calls.append(("transaction", sql, params))
        self.db.maybe_raise(sql)
        if sql.lstrip().upper().startswith("INSERT"):
            self.lastrowid = self.db.next_id()


class FakeDB:
    """Records every statement the app runs and answers queries from rules the test registers."""

    def __init__(self):
        self.rules = []
        self.errors = []
        self.calls = []
        self._next_id = 100

    # --- test setup helpers ---
    def when(self, pattern, rows):
        """Queries whose SQL matches `pattern` return `rows` (a list of dicts, or a function(sql, params))."""
        self.rules.append((re.compile(pattern, re.I | re.S), rows))

    def fail_on(self, pattern, error):
        """Any statement whose SQL matches `pattern` raises `error`."""
        self.errors.append((re.compile(pattern, re.I | re.S), error))

    def statements(self, kind=None, containing=""):
        return [c for c in self.calls if (kind is None or c[0] == kind) and containing.lower() in str(c[1]).lower()]

    # --- internals ---
    def next_id(self):
        self._next_id += 1
        return self._next_id

    def maybe_raise(self, sql):
        for pattern, error in self.errors:
            if pattern.search(sql):
                raise error

    # --- the functions app.py imports from db.py ---
    def query(self, sql, params=(), one=False):
        self.calls.append(("query", sql, params))
        self.maybe_raise(sql)
        rows = []
        for pattern, value in reversed(self.rules):  # the most recently registered matching rule wins
            if pattern.search(sql):
                rows = value(sql, params) if callable(value) else value
                break
        rows = list(rows)
        if one:
            return rows[0] if rows else None
        return rows

    def execute(self, sql, params=()):
        self.calls.append(("execute", sql, params))
        self.maybe_raise(sql)
        return self.next_id()

    def update_row(self, table, key_column, key_value, updates):
        self.calls.append(("update_row", table, key_column, key_value, dict(updates)))
        self.maybe_raise("UPDATE " + table)

    @contextmanager
    def transaction(self):
        yield FakeCursor(self)


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    for name in ("query", "execute", "transaction", "update_row"):
        monkeypatch.setattr(app_module, name, getattr(fake, name))
    return fake


@pytest.fixture
def client(db):  # depends on `db` so a test can never reach a real database by accident
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def bearer(id_field, id_value, role):
    return {"Authorization": "Bearer " + app_module.make_token(id_field, id_value, role)}


@pytest.fixture
def member_headers():
    return bearer("user_id", 7, "member")


@pytest.fixture
def admin_headers():
    return bearer("admin_id", 1, "admin")
