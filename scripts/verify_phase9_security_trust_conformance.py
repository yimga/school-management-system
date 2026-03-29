#!/usr/bin/env python3
"""
Phase 9 gate (narrow): security / trust surface contracts, trust-hub doc anchors,
and allowlist artifact presence.

Does not run ledger freshness (--check), lints, or pytest — those stay on
``test_phase9_security_gates`` / pre_deploy_gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    errors: list[str] = []

    super_trust = ROOT / "templates" / "schools" / "super_trust_center.html"
    tenant_trust = ROOT / "templates" / "accounts" / "security_trust_hub.html"
    ledger_script = ROOT / "scripts" / "build_phase8_security_ledger.py"
    csrf_json = ROOT / "scripts" / "allowlists" / "csrf_exempt_allowlist.json"
    allow_any_json = ROOT / "scripts" / "allowlists" / "allow_any_allowlist.json"
    raw_sql_json = ROOT / "scripts" / "allowlists" / "raw_sql_allowlist.json"
    north_star_doc = ROOT / "docs" / "NORTH_STAR_TRUST_AND_OPS.md"
    threat_model_doc = ROOT / "docs" / "THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md"

    paths = (
        super_trust,
        tenant_trust,
        ledger_script,
        csrf_json,
        allow_any_json,
        raw_sql_json,
        north_star_doc,
        threat_model_doc,
    )
    for p in paths:
        if not p.is_file():
            errors.append(f"Missing required file: {p.relative_to(ROOT).as_posix()}")

    if errors:
        print("verify_phase9_security_trust_conformance: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    super_text = _read(super_trust)
    for needle in (
        'extends "control_plane_base.html"',
        'data-page-archetype="decision-console"',
        'data-decision-engine="surface"',
        'phase8_dashboard_declaration "schools/super_trust_center.html"',
        "data-tour=",
    ):
        if needle not in super_text:
            errors.append(
                f"templates/schools/super_trust_center.html missing contract token: {needle!r}"
            )

    doc_anchors = (
        "NORTH_STAR_TRUST_AND_OPS.md",
        "THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md",
    )
    for anchor in doc_anchors:
        if anchor not in super_text:
            errors.append(
                f"templates/schools/super_trust_center.html missing trust doc anchor: {anchor!r}"
            )

    hub_text = _read(tenant_trust)
    for needle in (
        'extends "portal_base.html"',
        'data-decision-engine="surface"',
        'phase8_dashboard_declaration "accounts/security_trust_hub.html"',
        "server-side only",
    ):
        if needle not in hub_text:
            errors.append(
                f"templates/accounts/security_trust_hub.html missing contract token: {needle!r}"
            )

    if errors:
        print("verify_phase9_security_trust_conformance: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        "verify_phase9_security_trust_conformance: PASS "
        "(trust hub templates + doc anchors + allowlist JSON presence; ledger/lint gates separate)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
