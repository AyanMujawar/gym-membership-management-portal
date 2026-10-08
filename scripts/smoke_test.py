#!/usr/bin/env python3
"""End-to-end smoke test for a running Gym Portal.

    python scripts/smoke_test.py http://localhost          # Docker Compose
    python scripts/smoke_test.py http://localhost:8080     # Kubernetes (port-forward)
    python scripts/smoke_test.py http://<server-ip>        # the live AWS server

The same script runs in all three places, so "it works" means the same thing everywhere. It goes through
the public entry point only (nginx), exercises a whole member journey, and deletes the test member afterwards,
so it is safe to run against a live system. Exit code 0 = every check passed.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

failures = []


def check(name, condition, detail=""):
    print(("PASS  " if condition else "FAIL  ") + name + ("" if condition else f"   -> {detail}"))
    if not condition:
        failures.append(name)
    return condition


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def call(self, path, method="GET", body=None, token=None, raw=False):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                status, payload = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, payload = error.code, error.read()
        if raw:
            return status, payload.decode(errors="replace")
        try:
            return status, json.loads(payload)
        except ValueError:
            return status, {"_raw": payload.decode(errors="replace")[:200]}


def wait_until_ready(client, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if client.call("/api/health/ready")[0] == 200:
                return True
        except OSError:
            pass
        time.sleep(3)
    return False


def run(base, wait):
    client = Client(base)
    admin_email = os.environ.get("SMOKE_ADMIN_EMAIL", "admin@gym.com")
    admin_password = os.environ.get("SMOKE_ADMIN_PASSWORD", "Admin@123")
    member_email = os.environ.get("SMOKE_MEMBER_EMAIL", "demo@member.com")
    member_password = os.environ.get("SMOKE_MEMBER_PASSWORD", "Member@123")

    print(f"Smoke test against {base}\n")
    if not check("API becomes ready (database reachable)", wait_until_ready(client, wait),
                 f"not ready after {wait}s"):
        return

    # --- the site and the public surface ---
    status, page = client.call("/", raw=True)
    check("frontend serves the home page", status == 200 and "FitZone" in page, status)
    status, _ = client.call("/api/health/live")
    check("liveness probe", status == 200, status)
    check("backend metrics are NOT reachable from outside", client.call("/metrics", raw=True)[0] == 404)
    status, plans = client.call("/api/plans")
    check("plans are listed", status == 200 and isinstance(plans, list) and len(plans) >= 1, status)

    # --- seeded logins ---
    status, admin = client.call("/api/admin/login", "POST", {"email": admin_email, "password": admin_password})
    check("admin can log in", status == 200 and "token" in admin, status)
    status, demo = client.call("/api/users/login", "POST", {"email": member_email, "password": member_password})
    check("demo member can log in", status == 200 and "token" in demo, status)
    status, _ = client.call("/api/users/login", "POST", {"email": member_email, "password": "wrong-password"})
    check("wrong password is rejected", status == 401, status)
    if "token" not in admin or not plans:
        return

    # --- who may call what ---
    check("no token -> 401", client.call("/api/admin/dashboard")[0] == 401)
    if "token" in demo:
        check("member token cannot use admin API -> 403",
              client.call("/api/admin/dashboard", token=demo["token"])[0] == 403)
    check("admin token cannot use member API -> 403", client.call("/api/me", token=admin["token"])[0] == 403)

    status, dashboard = client.call("/api/admin/dashboard", token=admin["token"])
    check("admin dashboard loads", status == 200 and "monthly_revenue" in dashboard, status)
    status, report = client.call("/api/admin/report", token=admin["token"])
    check("admin report loads", status == 200 and "revenue_by_month" in report, status)

    # --- a whole member journey with a throwaway member, removed at the end ---
    email = f"smoke-{uuid.uuid4().hex[:10]}@example.com"
    new_user_id = None
    try:
        status, created = client.call("/api/users/register", "POST",
                                      {"name": "Smoke Test", "email": email, "password": "smoketest1"})
        new_user_id = created.get("user_id")
        check("new member registers", status == 201 and new_user_id, status)
        status, login = client.call("/api/users/login", "POST", {"email": email, "password": "smoketest1"})
        token = login.get("token")
        check("new member logs in", status == 200 and token, status)
        if not token:
            return

        plan_id = plans[0]["plan_id"]
        status, bought = client.call("/api/memberships", "POST", {"plan_id": plan_id, "method": "UPI"}, token)
        check("member buys a plan (simulated payment)", status == 201 and bought.get("txn_ref"), status)
        status, _ = client.call("/api/memberships", "POST", {"plan_id": plan_id, "method": "UPI"}, token)
        check("a second pending request is refused", status == 400, status)

        status, mine = client.call("/api/me/membership", token=token)
        check("membership shows as pending", status == 200 and mine.get("pending"), mine)
        membership_id = bought.get("membership_id")
        status, _ = client.call(f"/api/admin/memberships/{membership_id}", "PUT", {"status": "Approved"}, admin["token"])
        check("admin approves it", status == 200, status)
        status, mine = client.call("/api/me/membership", token=token)
        check("membership is now active", status == 200 and mine.get("active"), mine)

        status, renewal = client.call("/api/memberships", "POST", {"plan_id": plan_id, "method": "Card"}, token)
        check("member renews", status == 201, status)
        status, _ = client.call(f"/api/admin/memberships/{renewal.get('membership_id')}", "PUT",
                                {"status": "Approved"}, admin["token"])
        check("admin approves the renewal", status == 200, status)
        status, payments = client.call("/api/me/payments", token=token)
        check("payment history lists both payments", status == 200 and len(payments) == 2, payments)
    finally:
        if new_user_id:
            status, _ = client.call(f"/api/admin/members/{new_user_id}", "DELETE", token=admin["token"])
            check("test member is cleaned up", status == 200, status)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base_url", help="e.g. http://localhost or http://<server-ip>")
    parser.add_argument("--wait", type=int, default=90, help="seconds to wait for the API to become ready")
    args = parser.parse_args()
    run(args.base_url, args.wait)
    print()
    if failures:
        print(f"SMOKE TEST FAILED ({len(failures)}): " + "; ".join(failures))
        sys.exit(1)
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
