#!/usr/bin/env python3
"""
Enterprise buyer simulation — structural smoke only (no fake success).

Runs a narrow Django test subset, resolves critical platform URLs with Django
configured, records failures to docs/generated/kill_test_report.{json,md}.

Exit 1 when any critical scenario fails.

Windows / slow hosts: avoid fresh SQLite migrate/teardown stalls by reusing one DB:

  RMC_SQLITE_TEST_MEMORY=1 \\
  RMC_KILL_TEST_DB_FILE=.django_test_dbs/your_migrated.sqlite3 \\
  RMC_KILL_TEST_KEEPDB=1 \\
  python scripts/run_kill_test.py

Or: ``python scripts/run_kill_test.py --db-file .django_test_dbs/your_migrated.sqlite3 --keepdb``
(env vars ``RMC_KILL_TEST_*`` override defaults when CLI omitted).
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


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _report_path(path: str) -> str:
    p = Path(path)
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def _default_keepdb_path(dbs_dir: Path) -> str:
    migrated = dbs_dir / "ux_factory_reset.sqlite3"
    if migrated.exists() and migrated.stat().st_size > 0:
        return migrated.relative_to(ROOT).as_posix()
    return ".django_test_dbs/kill_test_recovery.sqlite3"


def main(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-file",
        default=None,
        help=(
            "SQLite path for both Django test subprocesses (serial). "
            "Relative paths resolve from repo root. Default: two fresh UUID-named files."
        ),
    )
    parser.add_argument(
        "--keepdb",
        action="store_true",
        help="Append --keepdb to manage.py test (recommended with --db-file on Windows).",
    )
    args = parser.parse_args(argv)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    exe = sys.executable
    dbs_dir = ROOT / ".django_test_dbs"
    dbs_dir.mkdir(parents=True, exist_ok=True)
    shared_raw = (args.db_file or os.environ.get("RMC_KILL_TEST_DB_FILE") or "").strip()
    use_keepdb = bool(args.keepdb) or _truthy_env("RMC_KILL_TEST_KEEPDB")
    if not shared_raw:
        # Windows agents repeatedly stalled on two fresh SQLite migrations with
        # captured subprocess output. Keep the same tests, but default to the
        # reliable file-backed keepdb path already documented above.
        shared_raw = _default_keepdb_path(dbs_dir)
        use_keepdb = True
    if shared_raw:
        p = Path(shared_raw)
        if not p.is_absolute():
            p = ROOT / p
        test_db_security = str(p)
        test_db_degraded = str(p)
        sqlite_mode = "shared_keepdb" if use_keepdb else "shared"
    else:
        # Fresh paths each run so parallel agents / hung processes do not lock the same
        # filenames during Django's test DB teardown (WinError 32 on Windows).
        run_id = uuid.uuid4().hex[:12]
        test_db_security = str(dbs_dir / f"kill_test_security_{run_id}.sqlite3")
        test_db_degraded = str(dbs_dir / f"kill_test_degraded_{run_id}.sqlite3")
        sqlite_mode = "ephemeral_pair"

    base_env = os.environ.copy()
    # Tests must use repo SQLite defaults; stray DATABASE_URL can block subprocess on Postgres.
    base_env.pop("DATABASE_URL", None)
    base_env.setdefault("RMC_TEST_LOCAL_SQLITE", "1")
    base_env.setdefault("RMC_SQLITE_TEST_MEMORY", "1")
    base_env.setdefault("RMC_RELIABLE_TEST_RUNNER", "1")
    base_env.setdefault("PYTHONUNBUFFERED", "1")

    extra_test_args: list[str] = []
    if use_keepdb:
        extra_test_args.append("--keepdb")

    scenarios: list[dict[str, object]] = []

    # Security regression bundle (tenant RBAC / surfaces — repo-contained).
    env_sec = {**base_env, "DJANGO_TEST_DB_FILE": test_db_security}
    print("Kill test: running security enforcement regression...", flush=True)
    proc_sec = subprocess.run(
        [
            exe,
            str(ROOT / "scripts/run_sqlite_memory_tests.py"),
            "apps.security.tests.test_security_enforcement",
            "apps.security.tests.test_absolute_security_enforcement",
            "apps.security.tests.test_tenant_route_leakage",
            "--verbosity=1",
            *extra_test_args,
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
    print("Kill test: resolving critical routes...", flush=True)
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
    print("Kill test: running degraded founder surface fallback...", flush=True)
    proc_degraded = subprocess.run(
        [
            exe,
            str(ROOT / "scripts/run_sqlite_memory_tests.py"),
            "apps.schools.tests.test_founder_dashboard",
            "--verbosity=1",
            *extra_test_args,
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
        "sqlite_mode": sqlite_mode,
        "django_test_db_file": test_db_security
        if test_db_security == test_db_degraded
        else {"security": _report_path(test_db_security), "degraded": _report_path(test_db_degraded)},
        "keepdb": use_keepdb,
        "scenarios": scenarios,
    }
    if isinstance(out["django_test_db_file"], str):
        out["django_test_db_file"] = _report_path(out["django_test_db_file"])
    gen = ROOT / "docs" / "generated"
    _write(out, gen)
    print(f"Kill test: {out['result']} ({gen / 'kill_test_report.json'})")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
