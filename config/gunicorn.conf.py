# Gunicorn config for Render and other PaaS.
# Ensures HTTP binds to 0.0.0.0:PORT so the platform's port scan detects the service.
import os
import re

port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"
# gthread: one worker can serve /health/ while a heavy /super/ request runs (I/O releases GIL).
# Default 1 worker + 4 threads fits Render free-tier RAM better than 2 sync workers.
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread")


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    match = re.match(r"\s*(\d+)", str(raw))
    if not match:
        return default
    return int(match.group(1))


workers = _int_env("WEB_CONCURRENCY", 1)
threads = _int_env("GUNICORN_THREADS", 4)
timeout = _int_env("GUNICORN_TIMEOUT", 120)
accesslog = "-"
errorlog = "-"
