# Gym Membership Management Portal

A web app that digitizes a local gym's membership handling: members register, buy and renew plans, and track payments online, while the gym admin approves memberships, manages members and plans, and watches a live dashboard. It replaces registers and spreadsheets.

It is also a **DevOps project**: every change travels from `git push` to production through an automated pipeline, and the running system is monitored with alerts and defined reliability targets.

## Features

**Member**: register and log in; browse plans and buy one (simulated payment); view membership details and days left; renew; payment history; update profile and password.

**Admin** (seeded account, since gym staff are not public sign-ups): dashboard (total, active and expired memberships, monthly revenue, pending approvals); approve or reject membership requests (rejecting refunds the payment); add, edit, delete and search members; manage plans; expired-membership list; one-page printable report.

## The DevOps pipeline

```
Developer --git push--> GitHub --> GitHub Actions
                                     |
        lint, Bandit, pip-audit, unit tests (99 tests, 99% coverage, gate 85%)
        Terraform / Ansible / Compose / Kubernetes / Prometheus config checks
                                     |
        build Docker images once  --> Trivy vulnerability scan (fails on fixable CRITICAL)
                                     |
        +-- integration test on Docker Compose ------+
        +-- integration test on Kubernetes (kind) ---+
                                     |
        push the tested images to GHCR (tag = commit SHA)
                                     |  main only
        Ansible deploys that exact tag to AWS EC2 (created by Terraform)
                                     |
        smoke test against the live site --fails--> automatic rollback to the previous version
                                     |
        Prometheus + Grafana + Loki + Alertmanager watch the running system
```

| Stage | Tools | Where |
|---|---|---|
| Source control | Git, GitHub, branch and pull-request workflow | |
| CI: build, test, scan | GitHub Actions, flake8, Bandit, pip-audit, pytest, Trivy | `.github/workflows/ci-cd.yml` |
| Containers | Docker, Docker Compose, non-root images, gunicorn, nginx reverse proxy | `app/*/Dockerfile`, `docker-compose.yml` |
| Orchestration | Kubernetes (Deployments, probes, rolling updates, HPA, PVC, Kustomize) tested on kind in CI | `k8s/` |
| Infrastructure as code | Terraform: EC2, security group, Elastic IP, key pair | `terraform/` |
| Configuration management | Ansible: swap, secrets, pull images, health-checked deploy | `ansible/deploy.yml` |
| Registry | GitHub Container Registry, images tagged by commit SHA | |
| Monitoring and logs | Prometheus, Alertmanager, node-exporter, Grafana (dashboards as code), Loki + Promtail | `monitoring/` |
| SRE | SLOs and error budget, runbook, blameless post-mortem | `docs/` |

## Architecture

```
Browser --:80--> nginx (frontend container) --/api--> Flask + gunicorn (backend) --> MySQL (db)
                                                         |  /metrics (internal only)
Prometheus <-- scrapes backend and node-exporter         |  JSON logs
Grafana :3000 <-- Prometheus, Loki <-- Promtail <--------+
```

Only ports 22 (SSH), 80 (website) and 3000 (Grafana) are open. The API, MySQL, Prometheus and Alertmanager are not reachable from outside; nginx forwards `/api` internally.

## Run it locally

Needs Docker Desktop.

```bash
docker compose up --build -d          # the app and the monitoring stack
python scripts/smoke_test.py http://localhost
```

| What | URL |
|---|---|
| The app | http://localhost |
| Grafana (dashboards, logs) | http://localhost:3000 (`admin` / `admin` locally) |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9093 |

Tests: `cd app/backend && pip install -r requirements-dev.txt && pytest --cov`

Kubernetes (needs `kind`): `kind create cluster`, load the images with `kind load docker-image`, then `scripts/k8s-deploy.sh`.

## Demo logins

| Role | Email | Password | Notes |
|---|---|---|---|
| Admin | `admin@gym.com` | `Admin@123` | |
| Member | `demo@member.com` | `Member@123` | active Quarterly plan |
| Member | `priya@member.com` | `Member@123` | active Yearly, renewed earlier |
| Member | `arjun@member.com` | `Member@123` | active Half-Yearly |
| Member | `sneha@member.com` | `Member@123` | expires in 6 days |
| Member | `expired@member.com` | `Member@123` | expired 15 days ago |
| Member | `vikram@member.com` | `Member@123` | expired 40 days ago |
| Member | `neha@member.com` | `Member@123` | paid, **waiting for admin approval** |
| Member | `rohan@member.com` | `Member@123` | registered, no membership |

Change these before using the project for anything real.

## Security measures

Passwords hashed (scrypt); JWT login tokens with a role check on every route; members only ever see their own data (identity comes from the token); parameterised SQL everywhere; HTML escaped in the frontend; non-root containers; the service refuses to start in production with a default signing key; secrets come from GitHub Secrets and are written to a private `.env` by Ansible, never committed; dependency, code and image scanning in CI; IMDSv2 required on the server; least-exposure firewall.

## More documentation

- [docs/slo.md](docs/slo.md): service level objectives and the error budget
- [docs/runbook.md](docs/runbook.md): what to do for each alert, and how to roll back
- [docs/postmortem-2026-09-21-deploy-hang.md](docs/postmortem-2026-09-21-deploy-hang.md): a real incident and what changed because of it
