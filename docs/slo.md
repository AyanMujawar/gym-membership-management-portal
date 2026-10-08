# Service Level Objectives

How we decide whether the Gym Portal is "healthy enough", measured from the metrics the backend already exposes.

## Terms

| Term | Meaning | Here |
|---|---|---|
| **SLI** (indicator) | A number that measures one aspect of the service | Share of requests that succeed; share answered quickly; share of time the API is reachable |
| **SLO** (objective) | The target we promise ourselves for an SLI | The table below |
| **Error budget** | How much failure the SLO still allows | 100% minus the SLO |

## Objectives

| # | SLI | SLO | Window | How it is measured (PromQL) |
|---|---|---|---|---|
| 1 | **Availability**: the API is reachable | **99.5%** | 30 days | `avg_over_time(up{job="gym-backend"}[30d])` |
| 2 | **Success rate**: requests that do not fail with a 5xx | **99.5%** | 30 days | `1 - sum(increase(http_requests_total{status=~"5.."}[30d])) / sum(increase(http_requests_total[30d]))` |
| 3 | **Latency**: requests answered in under 500 ms | **95%** | 30 days | `sum(increase(http_request_duration_seconds_bucket{le="0.5"}[30d])) / sum(increase(http_request_duration_seconds_count[30d]))` |

Health probes and `/metrics` are excluded from the traffic panels so they cannot flatter the numbers.

## Error budget

At 99.5% over 30 days the service may be unavailable for
`30 days x 24 h x 60 min x 0.5% = 216 minutes` (about **3.6 hours**) per month.

- **Budget healthy**: ship changes normally.
- **Budget more than half used**: slow down risky changes and look at what is eating it.
- **Budget exhausted**: freeze feature work until reliability is back; only fixes go out.

## How the alerts map to the SLOs

| Alert | Fires when | Protects SLO |
|---|---|---|
| `ServiceDown` | the backend cannot be scraped for 1 minute | 1 (availability) |
| `HighErrorRate` | more than 5% of requests are 5xx for 2 minutes | 2 (success rate) |
| `HighLatency` | the 95th percentile is above 500 ms for 5 minutes | 3 (latency) |
| `LoginFailureSpike` | more than 20 failed logins in 5 minutes | security (not an SLO) |
| `HighMemoryUsage` | server memory above 85% for 5 minutes | leading indicator: memory exhaustion caused our only real incident ([post-mortem](postmortem-2026-09-21-deploy-hang.md)) |

The thresholds are deliberately much stricter than the SLO targets, so the alert fires while there is still budget left to spend.

## Where to see it

The **Gym Portal - Service Overview** dashboard in Grafana has a row, "Service level objectives", that shows all three SLIs for whatever time range is selected, coloured green or red against the targets.

## Honest limits

- This is a single small server, so 99.5% is realistic; it is not a high-availability design.
- The dashboard evaluates the SLOs over the selected range (the time Prometheus has retained, 7 days), not a true rolling 30 days.
- Alerts use simple thresholds; a production setup would use multi-window burn-rate alerts.
