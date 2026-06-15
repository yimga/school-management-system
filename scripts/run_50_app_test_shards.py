#!/usr/bin/env python3
"""
Run the 50-app Django test matrix in serial shards; write completion proof.

Usage:
  python scripts/run_50_app_test_shards.py --write
  python scripts/run_50_app_test_shards.py --write --shard 0
  python scripts/run_50_app_test_shards.py --write --max-shards 2
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE_SESSION_ID = os.environ.get("RMC_50_APP_GATE_SESSION", "final_100_test_matrix")
OUT = REPO / "docs" / "generated"


def _repo_python() -> str:
    override = os.environ.get("RMC_TEST_PYTHON", "").strip()
    if override:
        return override
    for candidate in (
        REPO / ".venv" / "Scripts" / "python.exe",
        REPO / ".venv" / "bin" / "python",
    ):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


PYTHON = _repo_python()

# Import gate bootstrap so all shards share one stable SQLite test DB (no parallel fresh DBs).
sys.path.insert(0, str(REPO / "scripts"))
from bootstrap_sqlite_test_template import bootstrap_template  # noqa: E402
from sqlite_gate_db import (  # noqa: E402
    bootstrap_gate_session_env,
    reap_all_stale_gate_locks,
    sqlite_gate_lease,
    _pid_is_alive,
)

_MATRIX_RUNNER_LOCK = REPO / ".django_test_dbs" / "matrix_runner.pid"


@contextmanager
def _matrix_runner_lock():
    """Refuse a second concurrent matrix — parallel runners corrupt SQLite on Windows."""
    _MATRIX_RUNNER_LOCK.parent.mkdir(parents=True, exist_ok=True)
    if _MATRIX_RUNNER_LOCK.is_file():
        try:
            other = int(_MATRIX_RUNNER_LOCK.read_text(encoding="utf-8").strip())
        except ValueError:
            other = 0
        if other and _pid_is_alive(other):
            print(
                f"Matrix runner already active (pid {other}). "
                "Stop it before starting another.",
                file=sys.stderr,
                flush=True,
            )
            sys.exit(2)
        try:
            _MATRIX_RUNNER_LOCK.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        fd = os.open(str(_MATRIX_RUNNER_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print(
            "Matrix runner already active (lock file present). "
            "Stop it before starting another.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(2)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
        handle.flush()

    def _release() -> None:
        try:
            if _MATRIX_RUNNER_LOCK.is_file():
                if _MATRIX_RUNNER_LOCK.read_text(encoding="utf-8").strip() == str(os.getpid()):
                    _MATRIX_RUNNER_LOCK.unlink(missing_ok=True)
        except OSError:
            pass

    atexit.register(_release)
    try:
        yield
    finally:
        atexit.unregister(_release)
        _release()

SHARDS: list[list[str]] = [
    [
        "apps.academics.tests",
        "apps.accounts.tests",
        "apps.admissions.tests",
        "apps.analytics.tests",
        "apps.api.tests",
        "apps.apicenter.tests",
        "apps.automation.tests",
        "apps.billing.tests",
    ],
    [
        "apps.brand_experience.tests",
        "apps.communication.tests",
        "apps.compliance.tests",
        "apps.customers.tests",
        "apps.customersuccess.tests",
        "apps.evals.tests",
        "apps.finance.tests",
        "apps.global_registries.tests",
    ],
    [
        "apps.integrations_marketplace.tests",
        "apps.interop.tests",
        "apps.lifecycle.tests",
        "apps.marketplace.tests",
        "apps.metadata.tests",
        "apps.migration_cloud.tests",
        "apps.observability.tests",
        "apps.orchestration.tests",
    ],
    [
        "apps.packages.tests",
        "apps.payroll.tests",
        "apps.people.tests",
        "apps.plans_entitlements.tests",
        "apps.platform_runtime.tests",
        "apps.policies.tests",
        "apps.policies_rules.tests",
        "apps.reports.tests",
    ],
    [
        "apps.requests.tests",
        "apps.runtime_blueprints.tests",
        "apps.safeguarding.tests",
        "apps.sales.tests",
        "apps.school_events.tests",
        "apps.schoolops.tests",
        "apps.schools.tests",
        "apps.security.tests",
    ],
    [
        "apps.setup_studio.tests",
        "apps.siteconfig.tests",
        "apps.student360.tests",
        "apps.studio_os.tests",
        "apps.sync_engine.tests",
        "apps.tenancy.tests",
    ],
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()




def _looks_like_stale_keepdb(tail: str) -> bool:
    """Detect corrupted --keepdb gate DB (common after interrupted matrix runs)."""
    needles = (
        "already exists",
        "no such table:",
        "database is locked",
        "disk I/O error",
    )
    lower = (tail or "").lower()
    return any(n in lower for n in needles)


def _run_shard(shard_index: int, labels: list[str], *, keepdb: bool, fresh: bool = False) -> dict:
    cmd = [
        PYTHON,
        str(REPO / "scripts/run_sqlite_memory_tests.py"),
        *labels,
        "--verbosity=1",
        "--noinput",
    ]
    if fresh:
        cmd.append("--fresh")
    elif keepdb:
        cmd.append("--keepdb")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=7200,
        )
        tail = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-4000:]
        return {
            "shard": shard_index,
            "labels": labels,
            "command": " ".join(cmd),
            "exit_code": proc.returncode,
            "ok": proc.returncode == 0,
            "output_tail": tail,
        }
    except subprocess.TimeoutExpired:
        return {
            "shard": shard_index,
            "labels": labels,
            "command": " ".join(cmd),
            "exit_code": -1,
            "ok": False,
            "error": "timeout_7200s",
        }


# ──────────────────────────────────────────────────────────────────────
# Per-app isolation mode
#
# The default shard mode runs ~8 apps in ONE process against ONE shared
# keepdb. That lets committed TransactionTestCase rows + module state bleed
# across apps, so tests that pass alone fail in the matrix (confirmed: the
# MFA /super/ nav suite is green in isolation but red in a shared shard).
# Per-app isolation gives every app its OWN test DB file in its OWN process,
# eliminating cross-app bleed — the only way the matrix can prove green
# honestly. Migration cost is paid ONCE into a clean template, then copied
# per app, so this is not 50× slower.
# ──────────────────────────────────────────────────────────────────────

_TEMPLATE_DB = REPO / ".django_test_dbs" / "iso_app_template.sqlite3"


def _flatten_apps() -> list[str]:
    return [label for shard in SHARDS for label in shard]


def _iso_db_path(app_label: str) -> Path:
    return REPO / ".django_test_dbs" / f"iso_{app_label.replace('.', '_')}.sqlite3"


def _rm_sqlite(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        f = Path(str(path) + suffix)
        try:
            if f.exists():
                f.unlink()
        except OSError:
            pass


def _isolated_env(db_file: Path) -> dict:
    env = os.environ.copy()
    env["RMC_SQLITE_TEST_MEMORY"] = "1"
    # File-backed TEST db so --keepdb reuses the copied template schema.
    env["RMC_SQLITE_TEST_USE_MEMORY_NAME"] = "0"
    env["DJANGO_TEST_DB_FILE"] = str(db_file)
    # Per-app isolation must NOT funnel through the shared gate-session DB.
    env.pop("RMC_SQLITE_GATE_SESSION", None)
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def _manage_test_cmd(labels: list[str]) -> list[str]:
    return [
        PYTHON,
        str(REPO / "manage.py"),
        "test",
        *labels,
        "--settings=config.settings",
        "--noinput",
        "--keepdb",
        "--verbosity=1",
    ]


def _seal_sqlite_wal(db_path: Path) -> None:
    """Fold WAL into the main file so file copies / backups are consistent."""
    import sqlite3

    if not db_path.is_file():
        return
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    for suffix in ("-wal", "-shm"):
        f = Path(str(db_path) + suffix)
        try:
            if f.exists():
                f.unlink()
        except OSError:
            pass


def _seal_template_wal() -> None:
    """Seal the shared per-app template before snapshot copies."""
    _seal_sqlite_wal(_TEMPLATE_DB)


def _copy_sqlite_snapshot(src: Path, dst: Path) -> bool:
    """Copy a SQLite DB via the backup API (safe under WAL / Windows)."""
    import sqlite3

    _rm_sqlite(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _seal_sqlite_wal(src)
    try:
        src_conn = sqlite3.connect(str(src))
        try:
            dst_conn = sqlite3.connect(str(dst))
            try:
                src_conn.backup(dst_conn)
                dst_conn.execute("PRAGMA journal_mode=DELETE")
                dst_conn.commit()
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
    except sqlite3.Error:
        _rm_sqlite(dst)
        return False
    _seal_sqlite_wal(dst)
    if not dst.is_file() or dst.stat().st_size < 1024:
        _rm_sqlite(dst)
        return False
    try:
        conn = sqlite3.connect(str(dst))
        try:
            ok = conn.execute("PRAGMA integrity_check").fetchone()
            if not ok or ok[0] != "ok":
                _rm_sqlite(dst)
                return False
        finally:
            conn.close()
    except sqlite3.Error:
        _rm_sqlite(dst)
        return False
    return True


def _template_usable() -> bool:
    """True when a sealed template snapshot exists and looks migrated."""
    if not _TEMPLATE_DB.is_file():
        return False
    try:
        return _TEMPLATE_DB.stat().st_size >= 1024 * 1024
    except OSError:
        return False


def _build_template_db(*, reuse_if_present: bool = False) -> bool:
    """Migrate one clean, data-free template DB to copy per app."""
    if reuse_if_present and _template_usable():
        _seal_template_wal()
        return True
    _rm_sqlite(_TEMPLATE_DB)
    try:
        ok = bootstrap_template(_TEMPLATE_DB, verbosity=0)
    except Exception:
        _rm_sqlite(_TEMPLATE_DB)
        return False
    if not ok or not _TEMPLATE_DB.is_file() or _TEMPLATE_DB.stat().st_size < 1024:
        _rm_sqlite(_TEMPLATE_DB)
        return False
    _seal_template_wal()
    return True


def _run_app_isolated(app_label: str, *, template_ready: bool = False) -> dict:
    iso_db = _iso_db_path(app_label)

    def _exec_manage(*, use_template: bool) -> dict:
        _rm_sqlite(iso_db)
        if use_template and template_ready and _TEMPLATE_DB.is_file():
            if not _copy_sqlite_snapshot(_TEMPLATE_DB, iso_db):
                _rm_sqlite(iso_db)
        env = _isolated_env(iso_db)
        cmd = _manage_test_cmd([app_label])
        try:
            with sqlite_gate_lease(iso_db):
                proc = subprocess.run(
                    cmd, cwd=str(REPO), capture_output=True, text=True, timeout=3600, env=env
                )
            tail = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-4000:]
            return {
                "shard": app_label,
                "labels": [app_label],
                "command": " ".join(cmd),
                "exit_code": proc.returncode,
                "ok": proc.returncode == 0,
                "output_tail": tail,
            }
        except subprocess.TimeoutExpired:
            return {
                "shard": app_label,
                "labels": [app_label],
                "command": " ".join(cmd),
                "exit_code": -1,
                "ok": False,
                "error": "timeout_3600s",
            }
        finally:
            _rm_sqlite(iso_db)

    def _exec_fresh_runner() -> dict:
        cmd = [
            PYTHON,
            str(REPO / "scripts/run_sqlite_memory_tests.py"),
            app_label,
            "--fresh",
            "--verbosity=1",
            "--noinput",
        ]
        env = os.environ.copy()
        env["RMC_SQLITE_TEST_MEMORY"] = "1"
        env["RMC_SQLITE_TEST_USE_MEMORY_NAME"] = "0"
        env["DJANGO_TEST_DB_FILE"] = str(iso_db)
        env.pop("RMC_SQLITE_GATE_SESSION", None)
        try:
            with sqlite_gate_lease(iso_db):
                proc = subprocess.run(
                    cmd, cwd=str(REPO), capture_output=True, text=True, timeout=3600, env=env
                )
            tail = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-4000:]
            return {
                "shard": app_label,
                "labels": [app_label],
                "command": " ".join(cmd),
                "exit_code": proc.returncode,
                "ok": proc.returncode == 0,
                "output_tail": tail,
            }
        except subprocess.TimeoutExpired:
            return {
                "shard": app_label,
                "labels": [app_label],
                "command": " ".join(cmd),
                "exit_code": -1,
                "ok": False,
                "error": "timeout_3600s",
            }
        finally:
            _rm_sqlite(iso_db)

    result = _exec_manage(use_template=True)
    if result.get("ok"):
        return result
    if _looks_like_stale_keepdb(result.get("output_tail", "")):
        retry = _exec_fresh_runner()
        retry["retried_with_fresh_runner"] = True
        return retry
    return result


def payload_apps(results: list[dict], apps: list[str]) -> dict:
    all_ran = len(results) == len(apps)
    all_green = bool(results) and all(r.get("ok") for r in results) and all_ran
    return {
        "generated_at": _now(),
        "isolation": "app",
        "shard_count": len(apps),
        "shards_run": len(results),
        "all_shards_green": all_green,
        "all_shards_executed": all_ran,
        "shards": results,
        "command_template": "python scripts/run_50_app_test_shards.py --write --isolation app",
    }


def _write_progress(payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "full_50_app_test_matrix_completion.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def payload_base(shard_results: list[dict], by_index: dict) -> dict:
    all_green = bool(shard_results) and all(r.get("ok") for r in shard_results)
    all_ran = len(shard_results) == len(SHARDS)
    return {
        "generated_at": _now(),
        "shard_count": len(SHARDS),
        "shards_run": len(shard_results),
        "all_shards_green": all_green and all_ran,
        "all_shards_executed": all_ran,
        "shards": shard_results,
        "command_template": "python scripts/run_50_app_test_shards.py --write",
    }


def _run_app_isolation_mode(args) -> int:
    reaped = reap_all_stale_gate_locks(REPO, stale_after=120.0)
    if reaped:
        print(f"Reaped {reaped} stale SQLite gate lock(s)", flush=True)

    apps = _flatten_apps()
    print(
        f"Per-app isolation: {len(apps)} apps; building clean migrated template...",
        flush=True,
    )
    template_ready = _build_template_db(reuse_if_present=args.reuse_template)
    if template_ready:
        print(f"Template DB ready: {_TEMPLATE_DB}", flush=True)
    else:
        print(
            "  ! template build failed; each app will migrate fresh (slower, still isolated)",
            flush=True,
        )

    # Resume support: reuse prior per-app results for unchanged labels.
    by_label: dict[str, dict] = {}
    p = OUT / "full_50_app_test_matrix_completion.json"
    if p.is_file():
        try:
            prior = json.loads(p.read_text(encoding="utf-8"))
            if prior.get("isolation") == "app":
                by_label = {
                    r["shard"]: r
                    for r in (prior.get("shards") or [])
                    if r.get("shard") in apps
                }
        except json.JSONDecodeError:
            by_label = {}

    for i, app in enumerate(apps):
        if (
            not getattr(args, "force", False)
            and by_label.get(app, {}).get("ok")
            and app in by_label
        ):
            print(f"App {i + 1}/{len(apps)}: {app} (skip — prior ok)", flush=True)
            continue
        print(f"App {i + 1}/{len(apps)}: {app}", flush=True)
        result = _run_app_isolated(app, template_ready=template_ready)
        by_label[app] = result
        print(
            f"  -> {app} ok={result.get('ok')} exit={result.get('exit_code')}",
            flush=True,
        )
        if args.write:
            ordered = [by_label[a] for a in apps if a in by_label]
            _write_progress(payload_apps(ordered, apps))

    ordered = [by_label[a] for a in apps if a in by_label]
    payload = payload_apps(ordered, apps)
    if args.write:
        _write_progress(payload)
        failing = [r["shard"] for r in ordered if not r.get("ok")]
        lines = [
            "# Full 50-app test matrix completion (per-app isolation)\n",
            f"Generated: {_now()}\n",
            f"- Apps: {payload['shards_run']}/{payload['shard_count']}",
            f"- All green: **{payload['all_shards_green']}**",
            f"- Failing apps: {', '.join(failing) if failing else '(none)'}",
        ]
        (OUT / "full_50_app_test_matrix_completion.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
    print(
        f"Matrix (per-app): {payload['shards_run']}/{payload['shard_count']} apps; "
        f"all_green={payload['all_shards_green']}",
        flush=True,
    )
    return 0 if payload["all_shards_green"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--shard", type=int, default=None, help="Run single shard index")
    parser.add_argument("--max-shards", type=int, default=None, help="Run first N shards only")
    parser.add_argument("--keepdb", action="store_true", default=True)
    parser.add_argument("--no-keepdb", action="store_true")
    parser.add_argument(
        "--isolation",
        choices=["shard", "app"],
        default="shard",
        help="shard = shared-DB shards (fast, bleed-prone); "
        "app = per-app isolated DB (bleed-free, proves green honestly)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Per-app isolation: re-run apps even when prior JSON marked ok",
    )
    parser.add_argument(
        "--reuse-template",
        action="store_true",
        help="Per-app isolation: skip template rebuild when iso_app_template.sqlite3 exists",
    )
    args = parser.parse_args()
    keepdb = args.keepdb and not args.no_keepdb

    with _matrix_runner_lock():
        if args.isolation == "app":
            return _run_app_isolation_mode(args)

        reaped = reap_all_stale_gate_locks(REPO, stale_after=120.0)
        if reaped:
            print(f"Reaped {reaped} stale SQLite gate lock(s)", flush=True)
        gate_db = bootstrap_gate_session_env(REPO, session_id=GATE_SESSION_ID)
        os.environ["RMC_SQLITE_TEST_MEMORY"] = "1"
        os.environ["RMC_SQLITE_TEST_USE_MEMORY_NAME"] = "0"
        print(f"Gate test DB: {gate_db}", flush=True)

        existing = {}
        p = OUT / "full_50_app_test_matrix_completion.json"
        if p.is_file():
            try:
                existing = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}

        shard_results: list[dict] = list(existing.get("shards") or [])
        by_index = {r["shard"]: r for r in shard_results if "shard" in r}

        indices = list(range(len(SHARDS)))
        if args.shard is not None:
            indices = [args.shard]
        elif args.max_shards is not None:
            indices = indices[: args.max_shards]

        for idx in indices:
            if idx < 0 or idx >= len(SHARDS):
                continue
            print(f"Shard {idx + 1}/{len(SHARDS)}: {', '.join(SHARDS[idx][:3])}...", flush=True)
            result = _run_shard(idx, SHARDS[idx], keepdb=keepdb)
            if not result.get("ok") and _looks_like_stale_keepdb(result.get("output_tail", "")):
                print(
                    "  -> stale gate keepdb detected; resetting session and retrying with --fresh",
                    flush=True,
                )
                gate_db = bootstrap_gate_session_env(
                    REPO, session_id=GATE_SESSION_ID, force_fresh=True
                )
                os.environ["DJANGO_TEST_DB_FILE"] = str(gate_db)
                print(f"  -> fresh gate test DB: {gate_db}", flush=True)
                result = _run_shard(idx, SHARDS[idx], keepdb=keepdb, fresh=True)
                result["retried_with_fresh_gate"] = True
            by_index[idx] = result
            shard_results = [by_index[i] for i in sorted(by_index)]
            print(
                f"  -> shard {idx} ok={result.get('ok')} exit={result.get('exit_code')}",
                flush=True,
            )

            if args.write:
                _write_progress(payload_base(shard_results, by_index))

        payload = payload_base(shard_results, by_index)

        if args.write:
            _write_progress(payload)
            lines = [
                f"- Shards: {payload['shards_run']}/{payload['shard_count']}",
                f"- All green: **{payload['all_shards_green']}**",
            ]
            for r in shard_results:
                lines.append(f"- Shard {r['shard']}: ok={r.get('ok')} exit={r.get('exit_code')}")
            (OUT / "full_50_app_test_matrix_completion.md").write_text(
                "# Full 50-app test matrix completion\n\n"
                + f"Generated: {_now()}\n\n"
                + "\n".join(lines)
                + "\n",
                encoding="utf-8",
            )

        print(f"Matrix: {payload['shards_run']}/{payload['shard_count']} shards; all_green={payload['all_shards_green']}")
        return 0 if payload["all_shards_green"] else 1


if __name__ == "__main__":
    sys.exit(main())
