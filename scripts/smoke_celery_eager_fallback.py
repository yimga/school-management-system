"""Smoke test: Celery eager-fallback when no broker is configured.

Settings decide ``CELERY_TASK_ALWAYS_EAGER`` at import time based on the
broker URL, so the behaviour can only be exercised by loading settings in a
fresh process per env combination. This spawns three subprocesses and asserts
the resolved flag for each:

    1. no broker                -> eager (work runs inline)
    2. broker configured        -> NOT eager (work is deferred to a worker)
    3. no broker + opt-out flag -> NOT eager (work stays PENDING)

Run:  python scripts/smoke_celery_eager_fallback.py
Exit: 0 on success, 1 on any mismatch.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Probe executed inside each child process. Prints a single line we can parse.
_PROBE = (
    "import django, os;"
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings');"
    "django.setup();"
    "from django.conf import settings;"
    "print('EAGER=' + str(bool(getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False))))"
)


def _resolve_eager(extra_env: dict[str, str]) -> bool:
    """Load settings in a child process with ``extra_env`` and return the flag."""
    env = dict(os.environ)
    # Start from a clean broker/test baseline so the parent's env can't leak in.
    for key in ("CELERY_BROKER_URL", "REDIS_URL", "RMC_DISABLE_EAGER_FALLBACK"):
        env.pop(key, None)
    # RUNNING_TESTS would force eager via the first branch and mask the logic.
    env.pop("RUNNING_TESTS", None)
    env["DJANGO_LOG_LEVEL"] = "CRITICAL"
    env.update(extra_env)

    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("EAGER="):
            return line.strip() == "EAGER=True"
    raise AssertionError(
        "probe produced no EAGER= line.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def main() -> int:
    cases = [
        ("no broker -> eager", {}, True),
        (
            "broker configured -> deferred",
            {"CELERY_BROKER_URL": "redis://localhost:6379/0"},
            False,
        ),
        (
            "no broker + opt-out -> PENDING",
            {"RMC_DISABLE_EAGER_FALLBACK": "1"},
            False,
        ),
    ]

    failures = 0
    for name, extra_env, expected in cases:
        actual = _resolve_eager(extra_env)
        ok = actual == expected
        failures += not ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: expected eager={expected}, got eager={actual}")

    total = len(cases)
    passed = total - failures
    print(f"\n{passed}/{total} cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
