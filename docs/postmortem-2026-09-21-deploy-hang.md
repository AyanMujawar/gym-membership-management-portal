# Post-mortem: deployment hung for 10+ minutes on the 1 GB server

*Blameless format: we look at how the system allowed this, not at who ran what.*

| | |
|---|---|
| **Date** | 21 September 2026, about 19:00 UTC |
| **Severity** | Low: the live site stayed up; the deployment was badly delayed |
| **Duration** | The first deploy attempt ran for over 10 minutes without finishing (a normal deploy took about 1 minute) |
| **Status** | Resolved; the permanent fixes are part of the FA2 work |

## Summary

While re-deploying to the AWS server, the Ansible playbook sat on its first step (`apt update`) for more than ten minutes. The website kept answering with HTTP 200 the whole time. On inspection the server's load average was **35** on a machine with 2 vCPUs, memory was almost full and there was no swap. After about ten minutes the load fell and the deploy finished on its second run.

## Impact

- **Users**: none. The site and API kept serving requests.
- **Operators**: a 10+ minute delay to a routine deploy and an unclear picture of what was wrong.
- **Risk**: a server in this state could easily have crashed or stopped serving, with nobody alerted.

## Timeline

| Time (UTC, approx.) | Event |
|---|---|
| 19:00 | The deploy playbook starts; ping succeeds, then the `apt update` task does not return |
| 19:10 | Still stuck. The site returns 200, so the application is not down |
| 19:10 | Checking the server: load average 35.6 / 36.2 / 20.4, 914 MB RAM total with about 77 MB free, **no swap**, `kswapd0` (the memory-reclaim thread) active, `apt-check` in an uninterruptible state |
| 19:11 | A second playbook run is started and stalls on the same task; load has already fallen to 11 |
| 19:14 | The deploy completes; load average 1.3; all three containers healthy; the site was never down |

## Root cause

The server (`t3.micro`, 1 GB RAM) had **too little memory for what ran on it**: MySQL alone held about 40% of it, Docker and the application the rest. With **no swap**, any extra memory demand (here `apt update` and an automatic update check starting at the same moment) forced the kernel to reclaim memory constantly. The machine spent its time thrashing rather than working, so every command on it became extremely slow.

## Contributing factors

1. **No memory monitoring or alerting**: we only found out because a command was slow, and had to log in to investigate.
2. **Images were built on the server**, which is memory-hungry work for a 1 GB machine.
3. **No swap** as a safety net.
4. **No time limit** on deploy steps, so a stuck step simply waited.
5. **Only manual verification**: no automated check of the live site after a deploy.

## What went well

- The site kept serving traffic; containers were configured to restart automatically.
- Evidence was gathered before any change was made (load, memory, process states), which pointed straight at memory.
- Re-running the playbook was safe because it is idempotent.

## Action items (all addressed in FA2)

| Action | How it is addressed | Status |
|---|---|---|
| Give the server enough memory | Instance changed from `t3.micro` (1 GB) to `t3.small` (2 GB) in Terraform | Done |
| Add a swap safety net | The Ansible playbook creates and enables a 1 GB swap file | Done |
| Stop building images on the server | CI builds and tests the images once; the server only pulls them | Done |
| Alert before memory runs out | `HighMemoryUsage` alert (above 85% for 5 minutes) plus a Server memory panel | Done |
| Verify a deploy automatically | Post-deploy smoke test in the pipeline, with automatic rollback if it fails | Done |
| Make container health explicit | Health checks and `depends_on: service_healthy` ordering in Compose; liveness and readiness probes in Kubernetes | Done |
| Cap the monitoring stack's own memory use | `mem_limit` on every monitoring container | Done |

## Lessons

- A small machine failing slowly is harder to notice than one failing loudly, which is why **leading indicators** (memory, load) deserve alerts as much as "is it up?".
- **"The site is up" is not the same as "the system is healthy."**
- Automating the checks a person did by hand (smoke test, health checks, alerts) is what turns an accident into a non-event.
