# Gym Membership Management Portal

A web app that digitizes a local gym's membership handling: members register, buy and renew plans, and track payments online, while the gym admin approves memberships, manages members and plans, and watches a live dashboard. It replaces registers and spreadsheets.

Built as a DevOps project: the app is deployed to AWS with **Terraform** (creates the server), **Ansible** (configures it), and **Docker Compose** (runs it).

## Features

**Member**
- Register and log in
- Browse plans, buy one with a (simulated) online payment
- View membership details: plan, start/end date, days left
- Renew before or after expiry
- View payment history
- Update profile and password

**Admin** (seeded account — gyms don't let the public register as staff)
- Dashboard: total members, active memberships, expired memberships, monthly revenue, pending approvals
- Approve or reject membership requests (rejecting refunds the payment)
- Add / edit / delete members, with search
- Manage membership plans (add, edit, hide, delete)
- List of expired memberships to follow up on
- One-page report (revenue by month, plan popularity, expiring soon, all members) — printable / save as PDF

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, vanilla JavaScript, served by nginx |
| Backend | Python Flask REST API, JWT authentication |
| Database | MySQL 8 (tables: `admins`, `users`, `membership_plans`, `memberships`, `payments`) |
| Containers | Docker, Docker Compose |
| Infrastructure | Terraform (AWS EC2 + security group) |
| Configuration | Ansible (installs Docker, deploys the app) |

## DevOps Flow

```
Developer -> GitHub -> Terraform creates EC2 -> Ansible installs Docker
          -> Docker Compose deploys the Gym Portal -> Users open the website
```

## Demo Logins

| Role | Email | Password |
|---|---|---|
| Admin | `admin@gym.com` | `Admin@123` |
| Member (active plan) | `demo@member.com` | `Member@123` |
| Member (expired plan) | `expired@member.com` | `Member@123` |

Change these before using the project for anything real.

## Documentation

- [HOW_TO_RUN.md](HOW_TO_RUN.md) — run locally and deploy to AWS
- [ARCHITECTURE.md](ARCHITECTURE.md) — diagrams: pipeline, containers, database, flows
- [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md) — a script for presenting the project
