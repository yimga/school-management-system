#!/usr/bin/env python
"""Meta-gate: assert every critical CI gate stays WIRED into a workflow.

The architectural CI gates protect the code — but nothing protected the
*gates themselves* from being silently un-enforced. A peer edit to
``.github/workflows/ci.yml`` once dropped the ``verify_url_name_integrity``
step entirely: the verifier still existed, its baseline still said 0, its
tests still passed — but it no longer RAN on any PR, so a new
``NoReverseMatch`` could ship uncaught. That regression is invisible to every
other gate (they check code, not whether they're invoked).

This guard closes that meta-loophole. It holds a SOT registry of the gates
that MUST run on every PR and asserts each one's ``scripts/<gate>.py``
invocation appears in at least one workflow file under ``.github/workflows/``.
A gate missing from every workflow is a finding (exit 1).

Deliberately a pure-text scan (no YAML parse, no Django) so it runs in the
deps-free ``architectural-boundaries.yml`` boundary job alongside the static
scanners it protects. "Wired in ANY workflow" is the right contract — a gate
may legitimately move between workflow files, but it must never vanish from
all of them. Removing a gate on purpose is a reviewed change to
``REQUIRED_GATES`` here, which is exactly the audit trail we want.

Pass/fail gate (no finding-count baseline), like ``verify_slo_registry``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# SOT: gates that MUST be invoked on every PR. Each entry is the scanner's
# script path (the substring searched for in workflow files) + the workflow
# it is expected to live in (documentation / diagnostic only — the assertion
# is "present in SOME workflow"). Removing a gate from CI is a reviewed edit
# to this tuple.
REQUIRED_GATES: tuple[tuple[str, str], ...] = (
    # Reference-integrity family — the "literal string -> runtime registry ->
    # 500/silent" loophole class. All members must always run.
    ("scripts/scan_import_reference_integrity.py", "architectural-boundaries.yml"),
    ("scripts/verify_get_model_integrity.py", "ci.yml"),
    ("scripts/verify_url_name_integrity.py", "ci.yml"),
    ("scripts/verify_template_reference_integrity.py", "ci.yml"),
    ("scripts/verify_static_reference_integrity.py", "ci.yml"),
    ("scripts/verify_settings_key_integrity.py", "ci.yml"),
    ("scripts/verify_field_reference_integrity.py", "ci.yml"),
    ("scripts/verify_relation_path_integrity.py", "ci.yml"),
    # Documented-baseline drift meta-check (doc vs JSON).
    ("scripts/check_documented_baselines.py", "architectural-boundaries.yml"),
    # Template render safety + attribute-context layout-frame guard.
    ("scripts/audit_template_render_safety.py", "architectural-boundaries.yml"),
    ("scripts/scan_attribute_context_includes.py", "architectural-boundaries.yml"),
    # Money never float; tenant rows always scoped; offline label has code.
    ("scripts/scan_money_float.py", "architectural-boundaries.yml"),
    ("scripts/scan_tenant_queryset_safety.py", "tenant-isolation-scan.yml"),
    ("scripts/verify_offline_capability_implementation.py", "architectural-boundaries.yml"),
    # Tenant-facing money renders the locale currency, never a hardcoded symbol.
    ("scripts/scan_locale_display.py", "architectural-boundaries.yml"),
    # Global academic kernel — the canonical world grade-scale families must
    # stay seeded; without this gate a deploy could ship an empty registry and
    # the catalog's "9 world scales" claim becomes silent theater.
    ("scripts/verify_grading_scale_registry_coverage.py", "ci.yml"),
)


def _workflow_text() -> str:
    """Concatenated text of every workflow file (forward-slashed for matching)."""
    if not WORKFLOWS_DIR.is_dir():
        return ""
    chunks: list[str] = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml")):
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(chunks).replace("\\", "/")


def find_unwired(required=REQUIRED_GATES) -> list[dict]:
    """Return a finding per required gate whose invocation is in NO workflow."""
    haystack = _workflow_text()
    findings: list[dict] = []
    for script, expected_workflow in required:
        if script not in haystack:
            findings.append({"script": script, "expected_workflow": expected_workflow})
    return findings


def _payload(findings: list[dict]) -> dict:
    return {
        "rule": "every gate in REQUIRED_GATES must be invoked in at least one "
        ".github/workflows/*.yml file (prevents a gate from being silently "
        "un-enforced by an unrelated workflow edit)",
        "required_count": len(REQUIRED_GATES),
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings = find_unwired()
    if args.json:
        print(json.dumps(_payload(findings), indent=2, sort_keys=True))
        return 1 if findings else 0

    print(
        f"CI gate wiring: {len(REQUIRED_GATES)} required gate(s) checked, "
        f"{len(findings)} un-wired"
    )
    for f in findings:
        print(
            f"  MISSING: {f['script']} is in NO workflow "
            f"(expected in {f['expected_workflow']}) — gate is no longer enforced"
        )
    if findings:
        print(
            "\nA required gate vanished from every workflow. Re-wire it, or — if "
            "removal is intentional — drop it from REQUIRED_GATES in this script "
            "(a reviewed change)."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
