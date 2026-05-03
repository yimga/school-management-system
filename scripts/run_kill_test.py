#!/usr/bin/env python3
"""
Enterprise buyer simulation — structural smoke only (no fake success).

Runs a narrow Django test subset, resolves critical platform URLs with Django
configured, records failures to docs/generated/kill_test_report.{json,md}.

Exit 1 when any critical scenario fails.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _bootstrap_django():
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _reverse_many(names: list[tuple[str, tuple, dict]]) -> list[str]:
    from django.urls import NoReverseMatch, reverse

    failures: list[str] = []
    for name, args, kw in names:
        try:
            reverse(name, args=args, kwargs=kw)
        except NoReverseMatch as e:
            failures.append(f"{name}: {e}")
    return failures


def _write(out: dict, gen: Path) -> None:
    gen.mkdir(parents=True, exist_ok=True)
    p_json = gen / "kill_test_report.json"
    p_md = gen / "kill_test_report.md"
    p_json.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Kill test report",
        "",
        f"**Result:** {out['result']}",
        f"**Critical failures:** {out['critical_count']}",
        "",
    ]
    for s in out.get("scenarios", []):
        lines.append(f"## {s['id']}: {s['title']}")
        lines.append("")
        lines.append(f"- ok: **{s['ok']}**")
        for m in s.get("messages", []):
            lines.append(f"  - {m}")
        lines.append("")
    p_md.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    exe = sys.executable
    dbs_dir = ROOT / ".django_test_dbs"
    dbs_dir.mkdir(parents=True, exist_ok=True)
    # Fresh paths each run so parallel agents / hung processes do not lock the same
    # filenames during Django's test DB teardown (WinError 32 on Windows).
    run_id = uuid.uuid4().hex[:12]
    test_db_security = str(dbs_dir / f"kill_test_security_{run_id}.sqlite3")
    test_db_degraded = str(dbs_dir / f"kill_test_degraded_{run_id}.sqlite3")
    base_env = os.environ.copy()
    # Tests must use repo SQLite defaults; stray DATABASE_URL can block subprocess on Postgres.
    base_env.pop("DATABASE_URL", None)

    scenarios: list[dict[str, object]] = []

    # Security regression bundle (tenant RBAC / surfaces — repo-contained).
    env_sec = {**base_env, "DJANGO_TEST_DB_FILE": test_db_security}
    proc_sec = subprocess.run(
        [
            exe,
            str(ROOT / "manage.py"),
            "test",
            "apps.security.tests.test_security_enforcement",
            "apps.security.tests.test_absolute_security_enforcement",
            "apps.security.tests.test_tenant_route_leakage",
            "--noinput",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=3600,
        env=env_sec,
    )
    ok_sec = proc_sec.returncode == 0
    scenarios.append(
        {
            "id": "security_audit_smoke",
            "title": "Security enforcement regression",
            "ok": ok_sec,
            "messages": []
            if ok_sec
            else [(proc_sec.stderr or proc_sec.stdout or "")[-4000:]],
        }
    )

    critical_failures = sum(1 for s in scenarios if not s["ok"])

    route_msgs: list[str] = []
    try:
        _bootstrap_django()
        route_msgs = _reverse_many(
            [
                ("super:command_center", tuple(), {}),
                ("super:dashboard", tuple(), {}),
                ("super:founder_dashboard", tuple(), {}),
                ("siteconfig:tenant_runtime_configuration_hub", tuple(), {}),
            ]
        )
    except Exception as exc:
        route_msgs.append(f"django_bootstrap: {exc}")

    route_ok = len(route_msgs) == 0
    scenarios.append(
        {
            "id": "feature_route_resolution",
            "title": "Critical routes resolve (reverse)",
            "ok": route_ok,
            "messages": route_msgs or ["ok"],
        }
    )
    if not route_ok:
        critical_failures += 1

    env_deg = {**base_env, "DJANGO_TEST_DB_FILE": test_db_degraded}
    proc_degraded = subprocess.run(
        [
            exe,
            str(ROOT / "manage.py"),
            "test",
            "apps.schools.tests.test_founder_dashboard.FounderDashboardTests.test_dashboard_degrades_when_generated_json_missing",
            "--noinput",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=3600,
        env=env_deg,
    )
    degraded_ok = proc_degraded.returncode == 0
    scenarios.append(
        {
            "id": "degraded_surface_fallbacks",
            "title": "Founder surface degrades gracefully when generated ledgers are missing",
            "ok": degraded_ok,
            "messages": []
            if degraded_ok
            else [(proc_degraded.stderr or proc_degraded.stdout or "")[-4000:]],
        }
    )
    if not degraded_ok:
        critical_failures += 1

    overall_ok = critical_failures == 0
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if overall_ok else "FAIL",
        "critical_count": critical_failures,
        "scenarios": scenarios,
    }
    gen = ROOT / "docs" / "generated"
    _write(out, gen)
    print(f"Kill test: {out['result']} ({gen / 'kill_test_report.json'})")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
