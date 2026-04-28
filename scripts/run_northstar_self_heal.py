#!/usr/bin/env python3
"""
North Star self-heal orchestrator — conservative regeneration + ticket routing.

Runs mechanical verifiers after safe regenerations. Audit/kill scripts are recorded
as informational (they may fail until North Star slice queue is complete).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from northstar_common import (  # noqa: E402
    ensure_generated_dir,
    json_dump,
    repo_root,
    run_manage,
    run_script,
)
from northstar_self_heal_lib import (  # noqa: E402
    categorize_failure,
    write_ticket,
)


def _run_cmd(cmd: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=str(root), capture_output=True, text=True, check=False
    )


def main(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    exe = sys.executable
    root = repo_root()
    gen = ensure_generated_dir()
    tickets_dir = gen / "self_heal_tickets"

    informational: dict[str, int] = {}
    for label, rel in (
        ("run_northstar_audit", "scripts/run_northstar_audit.py"),
        ("run_kill_test", "scripts/run_kill_test.py"),
    ):
        cp = _run_cmd([exe, str(root / rel)], root)
        informational[label] = int(cp.returncode)

    gate_specs: list[tuple[str, list[str]]] = [
        (
            "audit_admin_gravity",
            [exe, str(root / "scripts" / "audit_admin_gravity.py"), "--strict"],
        ),
        (
            "audit_sitesettings_python_surface",
            [exe, str(root / "scripts" / "audit_sitesettings_python_surface.py")],
        ),
        ("audit_security_surface", [exe, str(root / "scripts" / "audit_security_surface.py")]),
        (
            "verify_shell_surface_inventory",
            [exe, str(root / "scripts" / "verify_shell_surface_inventory.py")],
        ),
        (
            "verify_design_system_phase2",
            [exe, str(root / "scripts" / "verify_design_system_phase2.py")],
        ),
        (
            "verify_doc_plan_density_discipline",
            [exe, str(root / "scripts" / "verify_doc_plan_density_discipline.py")],
        ),
        ("verify_sot_pillar_evidence", [exe, str(root / "scripts" / "verify_sot_pillar_evidence.py")]),
        ("verify_test_module_contract", [exe, str(root / "scripts" / "verify_test_module_contract.py")]),
        ("audit_post_surface", [exe, str(root / "scripts" / "audit_post_surface.py")]),
        ("audit_regional_ui_surface", [exe, str(root / "scripts" / "audit_regional_ui_surface.py")]),
        ("verify_rtl_major_templates", [exe, str(root / "scripts" / "verify_rtl_major_templates.py")]),
        (
            "verify_phase2_authenticated_shell_conformance",
            [exe, str(root / "scripts" / "verify_phase2_authenticated_shell_conformance.py")],
        ),
    ]

    failed_preflight: list[dict[str, str]] = []

    def note_gate_failure(label: str, cp: subprocess.CompletedProcess[str]) -> None:
        blob = (cp.stderr or "") + (cp.stdout or "")
        failed_preflight.append(
            {
                "name": label,
                "exit_code": str(cp.returncode),
                "category": categorize_failure(label, cp.stderr or "", cp.stdout or ""),
                "excerpt": blob[-4000:],
            }
        )

    for label, cmd in gate_specs:
        cp = _run_cmd(cmd, root)
        if cp.returncode != 0:
            note_gate_failure(label, cp)

    safe_fixes: list[str] = []
    inv = run_script("scripts/generate_platform_inventory.py", ["--write"])
    if inv.returncode == 0:
        safe_fixes.append("python scripts/generate_platform_inventory.py --write")

    i18n = run_manage("sync_i18n_catalog", "--compile")
    if i18n.returncode == 0:
        safe_fixes.append("python manage.py sync_i18n_catalog --compile")
        i18n_v = run_script("scripts/verify_i18n_catalog_fresh.py")
        if i18n_v.returncode != 0:
            note_gate_failure("verify_i18n_catalog_fresh", i18n_v)

    tickets: list[str] = []
    post_failures: list[dict[str, str]] = []
    for label, cmd in gate_specs:
        cp = _run_cmd(cmd, root)
        if cp.returncode == 0:
            continue
        cat = categorize_failure(label, cp.stderr or "", cp.stdout or "")
        blob = (cp.stderr or "") + (cp.stdout or "")
        excerpt = blob[-4000:]
        post_failures.append(
            {
                "name": label,
                "exit_code": str(cp.returncode),
                "category": cat,
                "excerpt": excerpt,
            }
        )
        if cat in (
            "permission_gap",
            "tenant_isolation_gap",
            "security_surface_gap",
            "post_surface_gap",
            "regional_ui_gap",
            "test_contract_gap",
        ):
            p = write_ticket(
                tickets_dir,
                category=cat,
                command=" ".join(cmd),
                excerpt=excerpt,
                cause="Verifier still failing after safe regenerations.",
                action="Fix product code or allowlist with review; do not silence the gate.",
                affected_files=[],
                risk="high",
                test_command=" ".join(cmd),
                timestamp=ts,
            )
            tickets.append(str(p))

    if not post_failures:
        status = "SELF_HEALED_PASS"
    elif tickets or any(
        f.get("category")
        in (
            "permission_gap",
            "tenant_isolation_gap",
            "security_surface_gap",
            "post_surface_gap",
            "regional_ui_gap",
            "test_contract_gap",
        )
        for f in post_failures
    ):
        status = "HUMAN_REVIEW_REQUIRED"
    else:
        status = "SELF_HEAL_FAILED"

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "informational_runs": informational,
        "gate_failures_before_safe_fixes": failed_preflight,
        "gate_failures_after_safe_fixes": post_failures,
        "safe_fixes_applied": safe_fixes,
        "unsafe_ticket_paths": tickets,
    }
    json_dump(out, gen / "northstar_self_heal_report.json")
    lines = [
        "# North Star self-heal",
        "",
        f"**Status:** {status}",
        "",
        "## Informational (audit / kill exit codes)",
        "",
    ]
    for k, v in sorted(informational.items()):
        lines.append(f"- {k}: {v}")
    lines.extend(
        [
            "",
            "## Safe fixes",
            "",
            "\n".join(f"- {s}" for s in safe_fixes) or "- (none)",
            "",
            "## Tickets",
            "",
            "\n".join(f"- `{t}`" for t in tickets) or "- (none)",
            "",
        ]
    )
    (gen / "northstar_self_heal_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Self-heal: {status} -> {gen / 'northstar_self_heal_report.json'}")
    return 0 if status == "SELF_HEALED_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
