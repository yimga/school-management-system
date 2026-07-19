#!/usr/bin/env python3
"""Postgres booking CI proof gate (#10 / #15 / #16).

Repo-scope PASS when:
  - Booking ExclusionConstraint tests exist (Postgres-only + SQLite capacity gate)
  - ``django-tests-postgres.yml`` wires a Postgres job that references booking proof

Reports ``EXTERNAL_ACTIONS_GREEN_REQUIRED`` when this machine cannot prove a green
GitHub Actions run for ``django-tests-postgres.yml`` (never invents a green run).

Optional ``--run-tests``: when ``DATABASE_URL`` is PostgreSQL, execute the
exclusion test classes (used by the CI workflow step).

Run: python scripts/verify_postgres_booking_ci_proof.py [--json] [--run-tests]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

WORKFLOW = ".github/workflows/django-tests-postgres.yml"
BOOKING_TEST = "apps/schoolops/tests/test_resource_booking.py"
BOOKING_MODEL = "apps/schoolops/models_resource_booking.py"
LAST_GREEN_ARTIFACT = "docs/generated/postgres_booking_ci_last_green.json"

# Labels executed when --run-tests is set on PostgreSQL.
RUN_TEST_LABELS = (
    "apps.schoolops.tests.test_resource_booking.ResourceBookingPostgresExclusionTests",
    "apps.schoolops.tests.test_resource_booking.ResourceBookingServiceTests",
)


def _file_exists(rel: str) -> bool:
    return (REPO_ROOT / rel).is_file()


def _read(rel: str) -> str:
    p = REPO_ROOT / rel
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def _file_contains(rel: str, needle: str) -> bool:
    return needle in _read(rel)


def _try_actions_green_via_artifact() -> tuple[bool, str]:
    """Committed artifact with a prior green run (operator-recorded, never faked)."""
    rel = LAST_GREEN_ARTIFACT
    if not _file_exists(rel):
        return False, f"{rel} absent"
    try:
        data = json.loads(_read(rel))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"{rel} unreadable: {exc}"
    conclusion = str(data.get("conclusion", "")).lower()
    workflow = str(data.get("workflow", ""))
    run_id = data.get("run_id") or data.get("databaseId")
    if conclusion != "success":
        return False, f"{rel} conclusion={conclusion!r} (need success)"
    if "django-tests-postgres" not in workflow and workflow != WORKFLOW:
        return False, f"{rel} workflow={workflow!r} (need django-tests-postgres)"
    if not run_id:
        return False, f"{rel} missing run_id"
    return True, f"artifact run_id={run_id} sha={data.get('head_sha', '?')}"


def _try_actions_green_via_gh() -> tuple[bool, str]:
    """Best-effort live query; absence of gh/network is not a gate failure."""
    try:
        result = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "--workflow=django-tests-postgres.yml",
                "--limit=5",
                "--json",
                "conclusion,databaseId,headSha,status,displayTitle",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        return False, f"gh unavailable: {exc}"
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()[:200]
        return False, f"gh run list failed: {err or result.returncode}"
    try:
        runs = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return False, "gh run list returned non-JSON"
    if not isinstance(runs, list) or not runs:
        return False, "gh run list empty (workflow may never have completed)"
    for run in runs:
        if str(run.get("conclusion", "")).lower() == "success":
            return True, (
                f"gh run_id={run.get('databaseId')} "
                f"sha={run.get('headSha', '?')}"
            )
    conclusions = [str(r.get("conclusion") or r.get("status")) for r in runs[:3]]
    return False, f"recent runs not success: {conclusions}"


def _prove_actions_green() -> tuple[bool, str, list[str]]:
    external: list[str] = []
    ok_art, detail_art = _try_actions_green_via_artifact()
    if ok_art:
        return True, detail_art, external
    ok_gh, detail_gh = _try_actions_green_via_gh()
    if ok_gh:
        return True, detail_gh, external
    external.append(
        "EXTERNAL_ACTIONS_GREEN_REQUIRED: Cannot prove a green GitHub Actions "
        "run for django-tests-postgres.yml from this machine "
        f"(artifact: {detail_art}; gh: {detail_gh}). "
        "Record a real success into docs/generated/postgres_booking_ci_last_green.json "
        "after Actions is green, or re-run with network + `gh` authenticated. "
        "Never invent a green run."
    )
    return False, "unproven", external


def _run_postgres_tests() -> int:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url.startswith("postgresql"):
        print(
            "verify_postgres_booking_ci_proof --run-tests: skip "
            "(DATABASE_URL is not PostgreSQL)",
            file=sys.stderr,
        )
        return 0
    cmd = [
        sys.executable,
        "manage.py",
        "test",
        *RUN_TEST_LABELS,
        "--tag=tenants_rls",
        "--settings=config.settings",
        "--verbosity=2",
        "--no-input",
    ]
    env = os.environ.copy()
    env.setdefault("USE_DJANGO_TENANTS", "0")
    result = subprocess.run(cmd, cwd=REPO_ROOT, env=env)
    if result.returncode != 0:
        print("POSTGRES_BOOKING_EXCLUSION_PROOF_FAIL", file=sys.stderr)
        return result.returncode
    print("POSTGRES_BOOKING_EXCLUSION_PROOF_PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--run-tests",
        action="store_true",
        help="On PostgreSQL DATABASE_URL, execute ExclusionConstraint test classes",
    )
    args = ap.parse_args(argv)

    checks: list[dict] = []
    external: list[str] = []

    # 1. Booking test module + Postgres ExclusionConstraint class
    test_exists = _file_exists(BOOKING_TEST)
    has_exclusion_class = _file_contains(
        BOOKING_TEST, "class ResourceBookingPostgresExclusionTests"
    )
    has_requires_postgres = _file_contains(BOOKING_TEST, "requires_postgres")
    has_pg_tag = _file_contains(BOOKING_TEST, "postgres_booking")
    has_integrity = _file_contains(BOOKING_TEST, "IntegrityError")
    has_sqlite_gate = _file_contains(
        BOOKING_TEST, "class ResourceBookingCapacityGateTests"
    )
    has_sqlite_tag = _file_contains(BOOKING_TEST, "sqlite_ok")
    checks.append(
        {
            "check": "booking_test_module",
            "pass": test_exists,
            "detail": BOOKING_TEST if test_exists else "MISSING",
        }
    )
    checks.append(
        {
            "check": "postgres_exclusion_tests",
            "pass": (
                has_exclusion_class
                and has_requires_postgres
                and has_pg_tag
                and has_integrity
            ),
            "detail": (
                "ResourceBookingPostgresExclusionTests + requires_postgres "
                "+ postgres_booking tag + IntegrityError"
                if (
                    has_exclusion_class
                    and has_requires_postgres
                    and has_pg_tag
                    and has_integrity
                )
                else "MISSING ExclusionConstraint Postgres proof class/tags"
            ),
        }
    )
    checks.append(
        {
            "check": "sqlite_capacity_gate_tests",
            "pass": has_sqlite_gate and has_sqlite_tag,
            "detail": (
                "ResourceBookingCapacityGateTests + sqlite_ok tag"
                if has_sqlite_gate and has_sqlite_tag
                else "MISSING SQLite capacity gate class/tag"
            ),
        }
    )

    # 2. Model ExclusionConstraint
    model_ok = _file_contains(BOOKING_MODEL, "ExclusionConstraint") and _file_contains(
        BOOKING_MODEL, "exclude_overlapping_resource_bookings"
    )
    checks.append(
        {
            "check": "model_exclusion_constraint",
            "pass": model_ok,
            "detail": (
                "ExclusionConstraint on ResourceBooking"
                if model_ok
                else f"MISSING in {BOOKING_MODEL}"
            ),
        }
    )

    # 3. Workflow wires Postgres job + booking proof
    wf_exists = _file_exists(WORKFLOW)
    wf_job = _file_contains(WORKFLOW, "django-postgres:")
    wf_service = _file_contains(WORKFLOW, "postgres:")
    wf_booking_proof = _file_contains(WORKFLOW, "verify_postgres_booking_ci_proof")
    wf_booking_tests = _file_contains(WORKFLOW, "test_resource_booking")
    checks.append(
        {
            "check": "workflow_exists",
            "pass": wf_exists,
            "detail": WORKFLOW if wf_exists else "MISSING",
        }
    )
    checks.append(
        {
            "check": "workflow_postgres_job",
            "pass": wf_job and wf_service,
            "detail": (
                "job django-postgres + postgres service"
                if wf_job and wf_service
                else "MISSING postgres job/service"
            ),
        }
    )
    checks.append(
        {
            "check": "workflow_booking_proof_wired",
            "pass": wf_booking_proof and wf_booking_tests,
            "detail": (
                "verify_postgres_booking_ci_proof + test_resource_booking"
                if wf_booking_proof and wf_booking_tests
                else "MISSING booking proof wiring"
            ),
        }
    )

    # 4. Companion shell + constraint static verifier
    shell_ok = _file_exists("scripts/run_postgres_booking_proof.sh")
    static_ok = _file_exists("scripts/verify_resource_booking_exclude_constraints.py")
    checks.append(
        {
            "check": "companion_scripts",
            "pass": shell_ok and static_ok,
            "detail": (
                "run_postgres_booking_proof.sh + verify_resource_booking_exclude_constraints.py"
                if shell_ok and static_ok
                else "MISSING companion script(s)"
            ),
        }
    )

    # 5. Actions green — honest EXTERNAL when unprovable
    actions_ok, actions_detail, actions_external = _prove_actions_green()
    checks.append(
        {
            "check": "actions_green_proof",
            "pass": True,  # classification only — never fails the gate
            "detail": (
                f"proven: {actions_detail}"
                if actions_ok
                else f"EXTERNAL (unproven): {actions_detail}"
            ),
        }
    )
    external.extend(actions_external)

    all_pass = all(c["pass"] for c in checks)
    report = {
        "gate": "verify_postgres_booking_ci_proof",
        "status": "PASS" if all_pass else "FAIL",
        "checks": checks,
        "external_remaining": external,
        "actions_green_proven": actions_ok,
        "summary": (
            "Repo booking ExclusionConstraint + Postgres CI wiring are sound. "
            + (
                "Actions green proven."
                if actions_ok
                else "Actions green is EXTERNAL_ACTIONS_GREEN_REQUIRED."
            )
            if all_pass
            else "Some repo-contained booking CI checks failed."
        ),
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = "PASS" if all_pass else "FAIL"
        print(f"verify_postgres_booking_ci_proof: {status}")
        for c in checks:
            mark = "OK" if c["pass"] else "FAIL"
            print(f"  [{mark}] {c['check']}: {c['detail']}")
        if external:
            print("\n  EXTERNAL (honest classification, not a gate failure):")
            for e in external:
                print(f"    - {e}")
        if all_pass:
            print("POSTGRES_BOOKING_CI_PROOF_PASS")

    if not all_pass:
        return 1

    if args.run_tests:
        return _run_postgres_tests()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
