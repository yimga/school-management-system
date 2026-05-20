#!/usr/bin/env python3
"""Tenant isolation certification from architecture review + in-repo gates.

Writes:
  docs/generated/tenant_isolation_certification.json
  docs/generated/tenant_isolation_certification.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCH_JSON = ROOT / "docs" / "generated" / "tenant_kernel_architecture_review.json"
CERT_JSON = ROOT / "docs" / "generated" / "tenant_isolation_certification.json"
CERT_MD = ROOT / "docs" / "generated" / "tenant_isolation_certification.md"


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _gate_checks() -> list[dict]:
    gates: list[dict] = []

    def add(gate_id: str, ok: bool, note: str) -> None:
        gates.append({"id": gate_id, "ok": ok, "note": note})

    code, _ = _run([sys.executable, str(ROOT / "scripts/scan_tenant_queryset_safety.py"), "--compare"])
    add("scan_tenant_queryset_safety_baseline_0", code == 0, "baseline 0, no new unscoped queries")

    code, _ = _run(
        [sys.executable, str(ROOT / "scripts/scan_tenant_isolation_marker_quality.py"), "--compare"]
    )
    add("scan_tenant_isolation_marker_quality", code == 0, "no lazy tenant-isolation-allow reasons")

    arch = ARCH_JSON
    add(
        "tenant_kernel_architecture_review",
        arch.is_file(),
        str(arch.relative_to(ROOT)).replace("\\", "/"),
    )

    mig = ROOT / "apps/schools/migrations/0048_force_rls_on_all_enabled_tables.py"
    add("force_rls_migration_tracked", mig.is_file(), "Postgres FORCE RLS migration present")

    return gates


def build_certification(arch: dict) -> dict:
    gates = _gate_checks()
    failed = [g for g in gates if not g["ok"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "TENANT ISOLATION KERNEL READY — REPO SCOPE"
        if not failed
        else "TENANT ISOLATION KERNEL NOT READY — REPO SCOPE",
        "repo_scope_only": True,
        "external_blockers": [
            "live_postgres_rls_ci_workflow_proof_on_render",
            "penetration_test_vendor_engagement",
        ],
        "architecture_ref": str(ARCH_JSON.relative_to(ROOT)).replace("\\", "/"),
        "architecture_generated_at": arch.get("generated_at"),
        "tenancy_mode": (arch.get("tenancy") or {}).get("tenancy_mode"),
        "gates": gates,
        "failed_gate_count": len(failed),
        "focused_test_modules": [
            "apps.security.tests.test_boundary_penetration",
            "apps.tenancy.tests.test_rls_boundary_contracts",
            "apps.accounts.tests.test_impersonation_audit_integrity",
            "apps.security.tests.test_tenant_route_leakage",
            "apps.security.tests.test_impersonation_approval",
        ],
    }


def _write_md(data: dict) -> str:
    lines = [
        "# Tenant isolation certification",
        "",
        f"**Generated:** {data['generated_at']}",
        f"**Verdict:** {data['verdict']}",
        "",
        f"Architecture: `{data['architecture_ref']}`",
        "",
        "## Gates",
        "",
        "| Gate | OK | Note |",
        "|------|----|------|",
    ]
    for g in data["gates"]:
        lines.append(f"| {g['id']} | {g['ok']} | {g['note']} |")
    lines.extend(["", "## External", ""])
    for item in data["external_blockers"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    _ = parser.parse_args()

    if not ARCH_JSON.is_file():
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts/generate_tenant_kernel_architecture_review.py"), "--write"],
            cwd=str(ROOT),
        )
    arch = json.loads(ARCH_JSON.read_text(encoding="utf-8"))
    data = build_certification(arch)
    CERT_JSON.parent.mkdir(parents=True, exist_ok=True)
    CERT_JSON.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    CERT_MD.write_text(_write_md(data), encoding="utf-8")
    print(f"Wrote {CERT_JSON.relative_to(ROOT)}")
    print(f"Verdict: {data['verdict']}")
    return 1 if data["failed_gate_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
