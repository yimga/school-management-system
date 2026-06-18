"""OSS load-test harness (Locust) — attendance + POS checkout smoke.

Install: ``pip install locust`` (Apache 2.0, free).

Run (example, against local dev server)::

    locust -f scripts/load/locustfile_attendance_wal.py \\
        --host=http://127.0.0.1:8000 \\
        --users 500 --spawn-rate 50

For 50k concurrent users, run distributed Locust workers behind your own
Caddy/nginx reverse proxy — no paid load-testing SaaS required.

Set env vars before run:
  RMC_LOAD_AUTH_TOKEN — Bearer JWT for a teacher/admin test user
  RMC_LOAD_SCHOOL_PATH — tenant path prefix, e.g. /t/demo-school
"""

from __future__ import annotations

import os

try:
    from locust import HttpUser, between, task
except ImportError:  # pragma: no cover — optional dev dependency
    HttpUser = object  # type: ignore[misc, assignment]
    between = task = lambda *a, **k: (lambda f: f)  # type: ignore[misc]


def _headers() -> dict[str, str]:
    token = os.environ.get("RMC_LOAD_AUTH_TOKEN", "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


class AttendanceWalUser(HttpUser):
    wait_time = between(0.05, 0.2)
    host = os.environ.get("RMC_LOAD_HOST", "http://127.0.0.1:8000")

    @task(3)
    def attendance_list(self) -> None:
        prefix = os.environ.get("RMC_LOAD_SCHOOL_PATH", "/t/demo-school")
        self.client.get(
            f"{prefix}/api/v1/attendance/",
            headers=_headers(),
            name="attendance_list",
        )

    @task(1)
    def pos_health(self) -> None:
        """Lightweight POS-adjacent endpoint — swap for POST checkout in staging."""
        prefix = os.environ.get("RMC_LOAD_SCHOOL_PATH", "/t/demo-school")
        self.client.get(
            f"{prefix}/authentication/backend/ops/pos/",
            headers=_headers(),
            name="pos_ops_page",
        )
