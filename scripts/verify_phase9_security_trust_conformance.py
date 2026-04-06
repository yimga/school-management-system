#!/usr/bin/env python3
"""
Phase 9 gate (narrow): security / trust surface contracts, trust-hub doc anchors,
and allowlist artifact presence.

Does not run ledger freshness (--check), lints, or pytest — those stay on
``test_phase9_security_gates`` / pre_deploy_gate.

Run (from repo root):
  python scripts/verify_phase9_security_trust_conformance.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root to inspect (default: directory containing this script's parent).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"--base directory not found: {raw_base}")
    return base


def main(argv: list[str] | None = None) -> int:
    try:
        base = _resolve_base(parse_args(argv).base)
    except ValueError as exc:
        print(f"verify_phase9_security_trust_conformance: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []

    super_trust = base / "templates" / "schools" / "super_trust_center.html"
    tenant_trust = base / "templates" / "accounts" / "security_trust_hub.html"
    ledger_script = base / "scripts" / "build_phase8_security_ledger.py"
    csrf_json = base / "scripts" / "allowlists" / "csrf_exempt_allowlist.json"
    allow_any_json = base / "scripts" / "allowlists" / "allow_any_allowlist.json"
    raw_sql_json = base / "scripts" / "allowlists" / "raw_sql_allowlist.json"
    north_star_doc = base / "docs" / "NORTH_STAR_TRUST_AND_OPS.md"
    threat_model_doc = base / "docs" / "THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md"

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
            errors.append(f"Missing required file: {p.relative_to(base).as_posix()}")

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
    raise SystemExit(main(None))
