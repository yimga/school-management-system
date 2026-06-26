#!/usr/bin/env python3
"""Preview Shell 100x Phase 4 gate — inner pages, pagination markers, empty partials."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "docs/generated/preview_shell_100x_parity_registry.json"


def _run(script: str, *args: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / script), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, "\n".join(out.strip().splitlines()[-6:])
    return True, out.strip().splitlines()[-1] if out.strip() else "ok"


def main() -> int:
    findings: list[str] = []

    # Empty-state partials retired 2026-06-26 (cp_empty / tp_empty / world_class_empty_state)
    # — superseded by the canonical components/rmc_empty_state.html; callers migrated.
    canonical_empty = "templates/components/rmc_empty_state.html"
    if not (ROOT / canonical_empty).is_file():
        findings.append(f"missing {canonical_empty}")

    data: dict = {}
    if not REGISTRY.is_file():
        findings.append("missing preview_shell_100x_parity_registry.json")
    else:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        targets = data.get("phase4_pagination_targets") or []
        if len(targets) < 30:
            findings.append(
                f"registry phase4_pagination_targets needs 30 entries (has {len(targets)})"
            )
        for rel in targets:
            path = ROOT / rel
            if not path.is_file():
                findings.append(f"missing pagination target: {rel}")
                continue
            body = path.read_text(encoding="utf-8", errors="replace")
            if 'data-rmc-scroll-policy="paginate"' not in body:
                findings.append(f"{rel}: missing data-rmc-scroll-policy=paginate")

        tenant_targets = data.get("phase4_tenant_portal_pagination_targets") or []
        if len(tenant_targets) < 30:
            findings.append(
                "registry phase4_tenant_portal_pagination_targets needs 30 entries "
                f"(has {len(tenant_targets)})"
            )
        for rel in tenant_targets:
            path = ROOT / rel
            if not path.is_file():
                findings.append(f"missing tenant pagination target: {rel}")
                continue
            body = path.read_text(encoding="utf-8", errors="replace")
            if 'data-rmc-scroll-policy="paginate"' not in body:
                findings.append(f"{rel}: missing data-rmc-scroll-policy=paginate")

    for rel in (
        "templates/archetypes/cp_operator_dashboard.html",
        "templates/archetypes/cp_admin_backoffice.html",
        "templates/archetypes/tp_role_home.html",
        "templates/archetypes/tp_task_list.html",
        "templates/archetypes/tp_form_wizard.html",
    ):
        if not (ROOT / rel).is_file():
            findings.append(f"missing archetype {rel}")

    if findings:
        print("verify_preview_shell_100x_phase4: FAIL (pre-flight)", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    for script, script_args in (
        ("scripts/verify_page_fold_standards.py", ("--write",)),
        ("scripts/audit_page_standards.py", ("--json", "docs/generated/page_standards_audit.json")),
        ("scripts/audit_luxury_ui_surface.py", ()),
    ):
        ok, detail = _run(script, *script_args)
        if not ok:
            findings.append(f"{script}: {detail}")

    if findings:
        print("verify_preview_shell_100x_phase4: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_preview_shell_100x_phase4: PREVIEW_SHELL_100X_PHASE4_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
