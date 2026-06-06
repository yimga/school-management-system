#!/usr/bin/env python3
"""Final poly-institution / global-governance closure sweep (mirrors CI job)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "generated" / "poly_institution_final_sweep_audit.json"

if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))
from sqlite_gate_db import bootstrap_gate_session_env, sqlite_sidecars_busy  # noqa: E402

# Mirrors `.github/workflows/architectural-boundaries.yml` global-governance-plan-completion.
STEPS: tuple[tuple[str, list[str]], ...] = (
    ("verify_country_governance_matrix.py", ["--require-verified", "--drift-check", "--write"]),
    ("verify_hierarchy_silo_drift.py", []),
    ("verify_global_operational_blind_spots.py", ["--granular-ops"]),
    ("verify_school_operating_modes.py", []),
    ("verify_org_lifecycle_events.py", []),
    ("verify_governance_doc_truth.py", []),
    ("verify_org_backfill_operator_smoke.py", ["--write"]),
    ("verify_scheduling_exclude_constraints.py", ["--write"]),
    ("verify_group_console_http_contract.py", ["--write"]),
    ("verify_multicampus_wedge_http_contract.py", ["--write"]),
    ("verify_global_governance_plan_completion.py", ["--strict", "--json"]),
    ("verify_doc_plan_density_discipline.py", []),
    ("verify_predeploy_core_gates.py", []),
)

POLY_UNIT_TESTS = (
    "apps.schools.tests.test_group_console",
    "apps.schools.tests.test_group_console_http",
    "apps.portal.tests.test_multicampus_wedge_http",
    "apps.interop.tests.test_transfer_apply",
    "apps.billing.tests.test_group_consolidation",
    "emis.tests.test_org_aggregate",
    "apps.people.tests.test_staff_compliance",
    "apps.schools.tests.test_governance_matrix_runtime",
    "apps.governance.tests.test_prompt_shaping_terminology",
    "apps.finance.tests.test_org_fx_rollup",
    "apps.schools.tests.test_context_profiles.ContextProfileServiceTests",
    "apps.registries.tests.test_seed_iso3166_subdivisions",
    "apps.governance.tests.test_models",
    "apps.siteconfig.tests.test_country_language_overlay_regression",
    "apps.academics.test_fractional_capacity",
    "apps.governance.tests.test_backfill_organizations",
    "apps.governance.tests.test_mat_groups_sync",
    "apps.academics.tests.test_scheduling_db_constraints",
    "apps.academics.tests.test_instruction_shift_conflicts",
)


def _warm_sqlite_gate_db() -> tuple[bool, str]:
    """One cold migrate for the shared gate session DB (Windows can exceed 15m)."""
    cmd = [
        sys.executable,
        str(REPO / "scripts" / "run_sqlite_memory_tests.py"),
        "apps.schools.tests.test_group_console_http",
        "--keepdb",
        "--verbosity=0",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=2400,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode == 0, tail[-500:] if tail else ""


def _run(script: str, extra: list[str], *, timeout: int = 900) -> tuple[bool, str]:
    cmd = [sys.executable, str(REPO / "scripts" / script), *extra]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode == 0, tail[-500:] if tail else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Poly-institution final closure sweep")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--skip-unit-tests", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    checks: list[dict[str, str]] = []

    stable = REPO / ".django_test_dbs" / "rmc_sqlite_test_runner.sqlite3"
    gate_db = bootstrap_gate_session_env(
        REPO,
        session_id="poly_institution_final_sweep",
        force_fresh=sqlite_sidecars_busy(stable),
    )
    print(f"verify_poly_institution_final_sweep: sqlite gate DB {gate_db}", flush=True)

    warm_ok, warm_proof = _warm_sqlite_gate_db()
    checks.append(
        {
            "id": "sqlite_gate_session_warm_migrate",
            "status": "PASS" if warm_ok else "FAIL",
            "proof": warm_proof,
        }
    )
    if not warm_ok:
        failures.append(f"sqlite gate session warm migrate failed: {warm_proof}")

    for script, extra in STEPS:
        if not warm_ok:
            break
        ok, proof = _run(script, extra)
        checks.append({"id": script, "status": "PASS" if ok else "FAIL", "proof": proof})
        if not ok:
            failures.append(f"{script} failed: {proof}")

    if not args.skip_unit_tests:
        cmd = [
            sys.executable,
            str(REPO / "scripts" / "run_sqlite_memory_tests.py"),
            *POLY_UNIT_TESTS,
            "--keepdb",
        ]
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        try:
            proc = subprocess.run(
                cmd, cwd=str(REPO), capture_output=True, text=True, timeout=1200, env=env
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            ok, proof = False, str(exc)
        else:
            ok = proc.returncode == 0
            proof = ((proc.stdout or "") + (proc.stderr or "")).strip()[-500:]
        checks.append({"id": "poly_unit_tests_bundle", "status": "PASS" if ok else "FAIL", "proof": proof})
        if not ok:
            failures.append(f"poly unit tests bundle failed: {proof}")

    # Regenerate closure map (non-fatal drift only).
    _run("generate_system_closure_map.py", ["--write"], timeout=120)

    verdict = (
        "POLY_INSTITUTION_FINAL_SWEEP_PASS"
        if not failures
        else "POLY_INSTITUTION_FINAL_SWEEP_FAIL"
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "finding_count": len(failures),
        "checks": checks,
        "failures": failures,
    }
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if failures:
        print(f"verify_poly_institution_final_sweep: {verdict}", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"verify_poly_institution_final_sweep: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
