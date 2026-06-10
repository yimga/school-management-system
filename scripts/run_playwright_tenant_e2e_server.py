#!/usr/bin/env python3
"""Boot Django for tenant phase1/phase2 Playwright (cross-platform, fast path)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("REDIS_URL", "")
    env.setdefault("RMC_FORCE_DB_SESSIONS", "1")
    env.setdefault("SECURE_SSL_REDIRECT", "0")
    env.setdefault("DEBUG", "1")
    env.setdefault("CSRF_COOKIE_SECURE", "0")
    env.setdefault("SESSION_COOKIE_SECURE", "0")
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def main() -> int:
    port = (os.environ.get("VISUAL_QA_PORT") or "8013").strip()
    slug = (os.environ.get("TENANT_SLUG") or "demo-school").strip()
    password = (os.environ.get("E2E_TENANT_PASSWORD") or "Test1234").strip()
    py = sys.executable
    env = _env()

    if os.environ.get("RMC_E2E_SKIP_MIGRATE") != "1":
        subprocess.check_call([py, "manage.py", "migrate", "--noinput"], cwd=REPO, env=env)

    subprocess.check_call(
        [
            py,
            "manage.py",
            "seed_demo_tenant_users",
            f"--school-slug={slug}",
            f"--password={password}",
        ],
        cwd=REPO,
        env=env,
    )

    os.execv(
        py,
        [py, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
    )
    return 0  # unreachable


if __name__ == "__main__":
    raise SystemExit(main())
