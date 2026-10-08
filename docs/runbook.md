# Runbook

What to do when something is wrong. Each alert links here by its section name.

**Where things are**

| What | Where |
|---|---|
| Website | `http://<server-ip>` |
| Grafana (dashboards, logs) | `http://<server-ip>:3000` (login: `admin` and the `grafana_admin_password` secret) |
| Prometheus / Alertmanager | not public; on the server `http://localhost:9090` / `:9093`, or from your laptop via an SSH tunnel: `ssh -L 9090:localhost:9090 -L 9093:localhost:9093 ubuntu@<server-ip>` |
| App folder on the server | `~/gym-membership-management-portal` (run `docker compose` commands there) |

**First look, always**

```bash
ssh -i ~/.ssh/gym-portal-key ubuntu@<server-ip>
cd gym-membership-management-portal
docker compose ps                      # which containers are up / healthy?
docker compose logs backend --tail 50  # what is the API saying?
```

## Incident process

1. **Detect**: an alert fires (Alertmanager / Grafana), or someone reports a problem.
2. **Triage**: open the Grafana dashboard. Is it the whole site or one feature? When did it start (did a deploy just happen)?
3. **Mitigate first, diagnose second**: restore service (restart, roll back), then find the cause.
4. **Verify**: run `python scripts/smoke_test.py http://<server-ip>` and watch the alert clear.
5. **Learn**: for anything that hurt users or burned error budget, write a blameless post-mortem (see [the example](postmortem-2026-09-21-deploy-hang.md)).

## ServiceDown

*The backend has been unreachable for over a minute.*

1. `docker compose ps`: is `backend` missing, restarting or unhealthy?
2. `docker compose logs backend --tail 100`: look for a crash, a failed start (e.g. `SECRET_KEY must be...`), or database errors.
3. Is the database up? `docker compose ps db`. The backend only reports ready once MySQL answers.
4. Quick fix: `docker compose up -d` (recreates anything missing) or `docker compose restart backend`.
5. Started right after a deploy? Roll back (below).

## HighErrorRate

*More than 5% of requests return a 5xx.*

1. Dashboard panel "5xx errors per second by endpoint": one endpoint, or all of them?
2. Grafana > Explore > Loki: `{compose_service="backend", level="ERROR"}` shows the stack traces.
3. All endpoints failing usually means the database: `docker compose logs db --tail 50`, disk full (`df -h`), memory (`free -m`).
4. One endpoint: likely a bug in the latest release. Roll back.

## HighLatency

*The 95th percentile response time is above 500 ms.*

1. Which endpoint is slow? Panel "Slowest endpoints (p95)".
2. Is the server short of CPU or memory? Panels in the "Server" row, or `docker stats --no-stream`.
3. Slow queries: run `docker compose exec db mysqladmin -uroot -p processlist` and look for long-running statements.
4. If memory is the cause, see `HighMemoryUsage`.

## LoginFailureSpike

*More than 20 failed logins in 5 minutes: possible password guessing.*

1. Loki: `{compose_service="backend"} |= "login failed"` shows how fast they arrive and for which role.
2. Is it a real user who forgot a password, or a script? Many failures in seconds is a script.
3. Mitigate: the app has no lockout yet. Block the source address in the security group if it is a single IP, and note it as a follow-up to add rate limiting.
4. Check no admin login succeeded unexpectedly: Grafana panel "Logins".

## HighMemoryUsage

*Server memory above 85% for 5 minutes.*

This is the early warning for the incident described in the [post-mortem](postmortem-2026-09-21-deploy-hang.md).

1. `free -m` and `docker stats --no-stream`: which container is using the memory?
2. Swap in use? `swapon --show`. Heavy swap use means the server is thrashing.
3. Restart the biggest consumer if it keeps growing: `docker compose restart <service>`.
4. Permanent fix: a larger instance (`instance_type` in `terraform/variables.tf`, then `terraform apply`).

## Rolling back a bad release

**Normally the pipeline does this itself**: if the post-deploy smoke test fails, it redeploys the previous version.

By hand (from WSL, in the `ansible` folder), redeploy any earlier commit:

```bash
ansible-playbook -i inventory.ini deploy.yml -e @secrets.yml \
  -e repo_version=<earlier-commit-sha> -e image_tag=<earlier-commit-sha>
```

Every image is tagged with its commit SHA, so any earlier release can be redeployed exactly as it was tested.

**Last resort, the original FA1 version** (builds on the server, port 5000 must be open in `terraform/variables.tf`):

```bash
ansible-playbook -i inventory.ini deploy.yml -e @secrets.yml -e repo_version=fa1-fallback -e image_tag=
```

## Data

- The database lives in the `mysql_data` Docker volume; it survives `docker compose down` and server reboots.
- `docker compose down -v` or `-e reset_database=true` **deletes it** and reseeds the demo data.
- There is no automatic backup. To take one: `docker compose exec db mysqldump -uroot -p gym_portal > backup.sql`.
