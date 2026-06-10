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
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE_SESSION_ID = os.environ.get("RMC_50_APP_GATE_SESSION", "final_100_test_matrix")
OUT = REPO / "docs" / "generated"

# Import gate bootstrap so all shards share one stable SQLite test DB (no parallel fresh DBs).
sys.path.insert(0, str(REPO / "scripts"))
from sqlite_gate_db import bootstrap_gate_session_env, reap_all_stale_gate_locks  # noqa: E402

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
        sys.executable,
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--shard", type=int, default=None, help="Run single shard index")
    parser.add_argument("--max-shards", type=int, default=None, help="Run first N shards only")
    parser.add_argument("--keepdb", action="store_true", default=True)
    parser.add_argument("--no-keepdb", action="store_true")
    args = parser.parse_args()
    keepdb = args.keepdb and not args.no_keepdb

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
