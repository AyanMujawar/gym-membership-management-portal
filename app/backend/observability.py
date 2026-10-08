"""Logging and metrics: the "eyes" of the running service.

Every request is counted and timed (Prometheus metrics at /metrics) and written as one JSON log line
(collected by Promtail into Loki). Endpoints are labelled by their route template, e.g.
/api/admin/members/<int:user_id>, never by the real URL, so the number of metric series stays small.
"""
import datetime
import json
import logging
import os
import sys
import time

from flask import Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter("http_requests_total", "HTTP requests handled", ["method", "endpoint", "status"])
LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency in seconds", ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
LOGINS = Counter("gym_logins_total", "Login attempts", ["role", "result"])
MEMBERSHIPS_REQUESTED = Counter("gym_memberships_requested_total", "Membership purchases and renewals requested")
PAYMENTS = Counter("gym_payments_total", "Simulated payments recorded", ["method"])
DECISIONS = Counter("gym_membership_decisions_total", "Admin decisions on pending memberships", ["decision"])

# Probes hit these every few seconds, so they are counted but not logged at INFO
QUIET_PATHS = ("/api/health", "/api/health/live", "/api/health/ready", "/metrics")


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so Loki can index the fields (level, path, status, ...)."""

    def format(self, record):
        entry = {
            "ts": datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    # We log requests ourselves, so the framework's own access log would only duplicate them
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def log_event(logger, level, msg, **fields):
    logger.log(level, msg, extra={"fields": fields})


def init_app(app):
    configure_logging()
    log = logging.getLogger("gym.request")

    @app.before_request
    def start_timer():
        g.started = time.perf_counter()

    @app.after_request
    def record_request(response):
        endpoint = request.url_rule.rule if request.url_rule else "unmatched"
        duration = time.perf_counter() - g.get("started", time.perf_counter())
        if endpoint != "/metrics":
            REQUESTS.labels(request.method, endpoint, str(response.status_code)).inc()
            LATENCY.labels(request.method, endpoint).observe(duration)
        level = logging.DEBUG if request.path in QUIET_PATHS else logging.INFO
        log_event(log, level, "request", method=request.method, path=request.path, endpoint=endpoint,
                  status=response.status_code, duration_ms=round(duration * 1000, 1))
        return response

    @app.route("/metrics", methods=["GET"])
    def metrics():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
