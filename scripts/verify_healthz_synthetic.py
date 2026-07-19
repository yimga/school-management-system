#!/usr/bin/env python
"""Metric #18 — synthetic /healthz probe (repo-contained, no external SaaS).

Calls the Django healthz view with mocked healthy deps and asserts HTTP 200,
then asserts configured Redis cache degraded → 503. Complements live deploy
synthetics (Pingdom etc.) which remain EXTERNAL.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main() -> int:
    import django

    django.setup()
    from django.test import RequestFactory

    from apps.observability.views import healthz

    factory = RequestFactory()
    db_ok = {"status": "healthy", "response_time_ms": 1.0, "connections": 0}

    with (
        patch("apps.observability.views.check_db_liveness", return_value=db_ok),
        patch(
            "apps.observability.views._check_cache_liveness",
            return_value={"status": "ok"},
        ),
        patch(
            "apps.observability.views._check_celery_broker_liveness",
            return_value={"status": "unavailable"},
        ),
        patch(
            "apps.observability.views._check_celery_queue_depth",
            return_value={"status": "unavailable"},
        ),
        patch("apps.observability.views._redis_cache_configured", return_value=False),
        patch("apps.observability.views.settings.CELERY_BROKER_URL", "", create=True),
    ):
        resp = healthz(factory.get("/healthz/"))
    if resp.status_code != 200:
        print(f"HEALTHZ_SYNTHETIC_FAIL: expected 200 got {resp.status_code}", file=sys.stderr)
        return 1
    body = json.loads(resp.content)
    if body.get("status") != "ok":
        print(f"HEALTHZ_SYNTHETIC_FAIL: status={body.get('status')}", file=sys.stderr)
        return 1

    with (
        patch("apps.observability.views.check_db_liveness", return_value=db_ok),
        patch(
            "apps.observability.views._check_cache_liveness",
            return_value={"status": "degraded"},
        ),
        patch(
            "apps.observability.views._check_celery_broker_liveness",
            return_value={"status": "ok"},
        ),
        patch(
            "apps.observability.views._check_celery_queue_depth",
            return_value={"status": "ok", "depth": 0},
        ),
        patch("apps.observability.views._redis_cache_configured", return_value=True),
        patch(
            "apps.observability.views.settings.CELERY_BROKER_URL",
            "redis://x:6379/0",
            create=True,
        ),
    ):
        resp = healthz(factory.get("/healthz/"))
    if resp.status_code != 503:
        print(f"HEALTHZ_SYNTHETIC_FAIL: expected 503 got {resp.status_code}", file=sys.stderr)
        return 1

    print("HEALTHZ_SYNTHETIC_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
