# Gunicorn config for Render and other PaaS.
# Ensures HTTP binds to 0.0.0.0:PORT so the platform's port scan detects the service.
import os

port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
accesslog = "-"
errorlog = "-"
