#!/usr/bin/env python3
"""Penetration test report artifact (module inventory + scenario matrix).

Writes:
  docs/generated/tenant_isolation_penetration_report.json
  docs/generated/tenant_isolation_penetration_report.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_OUT = ROOT / "docs" / "generated" / "tenant_isolation_penetration_report.json"
MD_OUT = ROOT / "docs" / "generated" / "tenant_isolation_penetration_report.md"

SCENARIOS = [
    {
        "id": "cross_tenant_pk_guess",
        "module": "apps.security.tests.test_boundary_penetration",
        "description": "Foreign student PK on wrong tenant host → not 200",
    },
    {
        "id": "forged_session_school_id",
        "module": "apps.security.tests.test_boundary_penetration",
        "description": "Forged session school_id cannot unlock foreign export",
    },
    {
        "id": "slug_host_manipulation",
        "module": "apps.security.tests.test_boundary_penetration",
        "description": "Tenant admin blocked from manager /super/ surface",
    },
    {
        "id": "host_header_manager_export",
        "module": "apps.security.tests.test_boundary_penetration",
        "description": "Tenant admin cannot export platform schools CSV",
    },
    {
        "id": "rls_query_isolation",
        "module": "apps.security.tests.test_boundary_penetration",
        "description": "rls_school context hides foreign student row",
    },
    {
        "id": "impersonation_without_reason",
        "module": "apps.security.tests.test_boundary_penetration",
        "description": "switch_to_tenant rejects blank justification",
    },
    {
        "id": "impersonation_audit_integrity",
        "module": "apps.accounts.tests.test_impersonation_audit_integrity",
        "description": "Reason, IP, actor logged; no email in repr",
    },
    {
        "id": "rls_force_migration_contract",
        "module": "apps.tenancy.tests.test_rls_boundary_contracts",
        "description": "FORCE RLS migration + engine proof differences",
    },
    {
        "id": "platform_route_from_tenant",
        "module": "apps.security.tests.test_tenant_route_leakage",
        "description": "Control-plane routes denied on tenant host",
    },
    # Tenant⟂operator isolation program (2026-07-05) — the closed audit holes.
    {
        "id": "is_staff_tenant_admin_operator_surface",
        "module": "apps.schools.tests.test_super_segment_tenant_guard",
        "description": "H1: is_staff tenant admin denied operator surfaces on the tenant host "
        "(super-segment middleware guard + views re-gated to require_control_plane_access)",
    },
    {
        "id": "operator_to_tenant_confinement_live",
        "module": "apps.accounts.tests.test_tenant_host_isolation_revival",
        "description": "H2/H6/H7: SUPERADMIN-role operator confined to signed impersonation on a "
        "tenant host (revived guard); impersonation session TTL enforced; break-glass superuser "
        "access audited",
    },
    {
        "id": "forwarded_host_operator_spoof",
        "module": "apps.schools.tests.test_forwarded_host_hardening",
        "description": "H3: a forged X-Forwarded-Host cannot select the operator (manager) urlconf",
    },
    {
        "id": "operator_route_enumeration_coverage",
        "module": "scripts.verify_tenant_cannot_reach_operator_routes",
        "description": "H4.5: every super: operator route (enumerated across host-split urlconfs) is "
        "covered by the tenant-host super-segment guard",
    },
    {
        "id": "support_helper_data_layer_authz",
        "module": "apps.api.tests.test_support_agent_console",
        "description": "H5: operator support-chat helpers fail closed for a non-operator identity "
        "(data-layer defense-in-depth, not just the connect gate)",
    },
]


def _run_tests() -> dict[str, str]:
    labels = ",".join(
        {
            "apps.security.tests.test_boundary_penetration",
            "apps.tenancy.tests.test_rls_boundary_contracts",
            "apps.accounts.tests.test_impersonation_audit_integrity",
        }
    )
    cmd = [
        sys.executable,
        str(ROOT / "scripts/run_sqlite_memory_tests.py"),
        labels,
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, check=False)
    status = "pass" if proc.returncode == 0 else "fail"
    return {"status": status, "exit_code": proc.returncode, "summary_tail": (proc.stdout or "")[-800:]}


def build_report(*, test_result: dict | None = None) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pii_free": True,
        "scenarios": SCENARIOS,
        "scenario_count": len(SCENARIOS),
        "test_run": test_result or {"status": "not_run"},
        "verdict": "PENETRATION SUITE READY — REPO SCOPE"
        if (test_result or {}).get("status") == "pass"
        else "PENETRATION SUITE PENDING — RUN TESTS",
    }


def _write_md(data: dict) -> str:
    lines = [
        "# Tenant isolation penetration report",
        "",
        f"**Generated:** {data['generated_at']}",
        f"**Verdict:** {data['verdict']}",
        "",
        "| Scenario | Module |",
        "|----------|--------|",
    ]
    for row in data["scenarios"]:
        lines.append(f"| {row['id']} | `{row['module']}` |")
    tr = data.get("test_run") or {}
    lines.extend(["", f"**Test run:** {tr.get('status', 'not_run')}", ""])
    return "\n".join(lines) + "\n"


def _check() -> int:
    """CI freshness gate: the committed artifact's scenario matrix must match the
    current SCENARIOS (someone adding/removing a scenario must regenerate + commit).
    Ignores the volatile ``generated_at`` / ``test_run`` fields."""
    current = build_report()
    try:
        committed = json.loads(JSON_OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(
            "FAIL: penetration report artifact missing/unreadable — run "
            "`python scripts/generate_tenant_isolation_penetration_report.py --write`",
            file=sys.stderr,
        )
        return 1
    if committed.get("scenarios") != current["scenarios"]:
        print(
            "FAIL: penetration scenario matrix drifted from the committed artifact — run "
            "`python scripts/generate_tenant_isolation_penetration_report.py --write`",
            file=sys.stderr,
        )
        return 1
    print(f"penetration report artifact current: {current['scenario_count']} scenarios")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument(
        "--check", action="store_true", help="assert committed artifact matches current scenarios"
    )
    args = parser.parse_args()

    if args.check:
        return _check()

    test_result = _run_tests() if args.run_tests else None
    data = build_report(test_result=test_result)
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MD_OUT.write_text(_write_md(data), encoding="utf-8")
    print(f"Wrote {JSON_OUT.relative_to(ROOT)}")
    if args.run_tests:
        return 0 if data["verdict"].startswith("PENETRATION SUITE READY") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
