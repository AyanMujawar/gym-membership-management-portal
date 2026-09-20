# Demo Walkthrough

A suggested 5–7 minute script for presenting the project. Start from a clean state: `docker compose down -v && docker compose up -d`.

## 1. The problem (30 sec)
Local gyms track memberships in registers and spreadsheets — renewals get missed, payments are hard to total. This portal digitizes it.

## 2. The DevOps pipeline (1–2 min)
Show [ARCHITECTURE.md](ARCHITECTURE.md) section 1, then, if deployed, the live AWS URL:
- **GitHub** holds the code
- **Terraform** (`terraform/main.tf`) creates the EC2 server and security group
- **Ansible** (`ansible/deploy.yml`) installs Docker and deploys the app
- **Docker Compose** (`docker-compose.yml`) runs frontend, backend and database containers

## 3. Member flow (2 min)
1. Open the site → show the plans on the home page
2. **Become a member** → register a new account
3. Choose a plan → simulated payment → "waiting for admin approval"
4. **My Membership** shows the pending request; **Payments** shows the transaction

## 4. Admin flow (2 min)
1. Log out; log in as `admin@gym.com` / `Admin@123`
2. **Dashboard** — total members, active, expired, monthly revenue; the new request is under Pending Approvals → **Approve**
3. Log back in as the new member: the membership is now Active with days left, and Renew is available
4. **Members** — search, add, edit, delete
5. **Plans** — add or hide a plan
6. **Expired** — `expired@member.com` shows up for follow-up
7. **Report** — the one-page report; **Print / Save as PDF**

## 5. Persistence (30 sec)
`docker compose down` then `docker compose up -d` — all data survives because the database lives on a Docker volume.

## Likely questions

| Question | Answer |
|---|---|
| How do you stop a member seeing someone else's data? | The user's identity comes from the signed JWT, never from the request |
| How do memberships expire without a scheduler? | Expiry is applied on every read (`expire_memberships()` in `app.py`) |
| Are payments real? | Simulated: a payment row is recorded, no gateway or card data |
| Why can't anyone register as admin? | Admin accounts are seeded in the database; there is no admin sign-up endpoint |
| What if an admin rejects a paid request? | The membership becomes Rejected and the payment is marked Refunded |
| How do you redeploy after a change? | `git push`, then re-run the Ansible playbook |
