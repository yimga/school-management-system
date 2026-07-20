#!/usr/bin/env python3
"""Record an honest local report-card moat proof artifact (#4).

Runs the Django staff-publish → parent PDF e2e tests. On success, writes
``docs/generated/report_card_moat_local_proof.json`` with LOCAL_MOAT_PASS.

Never invents Actions green. Playwright parent hash / armed runner remain
optional fields the operator can flip after a real local armed run.

Usage:
  python scripts/record_report_card_moat_local_proof.py
  python scripts/record_report_card_moat_local_proof.py --skip-tests  # rewrite only if prior pass
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "docs" / "generated" / "report_card_moat_local_proof.json"

DJANGO_LABELS = (
    "apps.reports.tests.test_report_card_e2e_flow",
    "apps.reports.tests.test_report_card_e2e_seed",
)


def _run_django_e2e() -> int:
    # Prefer manage.py + keepdb (Windows-friendly) over cold migrate.
    env = os.environ.copy()
    env.setdefault("RMC_SQLITE_TEST_MEMORY", "1")
    env.setdefault("RMC_SQLITE_TEST_USE_MEMORY_NAME", "0")
    env.setdefault("PYTHONUNBUFFERED", "1")
    if not env.get("DJANGO_TEST_DB_FILE", "").strip():
        env["DJANGO_TEST_DB_FILE"] = str(
            ROOT / ".django_test_dbs" / "report_card_moat_proof.sqlite3"
        )
    cmd = [
        sys.executable,
        str(ROOT / "manage.py"),
        "test",
        *DJANGO_LABELS,
        "--settings=config.settings",
        "--noinput",
        "--keepdb",
        "--parallel=1",
        "--verbosity=1",
    ]
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _write_artifact(*, django_ok: bool, note: str) -> None:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "LOCAL_MOAT_PASS" if django_ok else "LOCAL_MOAT_FAIL",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "django_e2e_ok": django_ok,
        "django_labels": list(DJANGO_LABELS),
        "playwright_parent_ok": False,
        "armed_runner_ok": False,
        "external_remaining": [
            "EXTERNAL_ACTIONS_GREEN_REQUIRED: Do not invent GitHub Actions "
            "tenant-moat-e2e success from this local proof.",
        ],
        "note": note,
    }
    ARTIFACT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {ARTIFACT.relative_to(ROOT)} status={payload['status']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--skip-tests",
        action="store_true",
        help="Do not re-run Django e2e; refuse to write PASS without a fresh run.",
    )
    args = ap.parse_args(argv)

    if args.skip_tests:
        print("Refusing --skip-tests: local moat PASS requires a fresh Django e2e run.")
        return 2

    print("Running Django report-card e2e labels…")
    rc = _run_django_e2e()
    django_ok = rc == 0
    _write_artifact(
        django_ok=django_ok,
        note=(
            "Staff publish→parent PDF proven via Django TestCase. "
            "Set playwright_parent_ok/armed_runner_ok after a real local armed run."
            if django_ok
            else "Django e2e failed — artifact records LOCAL_MOAT_FAIL."
        ),
    )
    return 0 if django_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
