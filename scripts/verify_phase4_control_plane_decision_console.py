#!/usr/bin/env python3
"""
Phase 4 gate: control-plane decision-console conformance on touched surfaces.

Enforces three non-negotiable contracts:
1) structured outcome groups are rendered from the shared outcomes partial
2) source tracing vocabulary and source-tracing step exist in control outcome model
3) publish/rollback affordances exist in operator model and surfaced outcomes
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_literal_value(module: ast.Module, name: str):
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return ast.literal_eval(node.value)
    raise KeyError(name)


def main() -> int:
    errors: list[str] = []

    ccc_tenant = ROOT / "templates" / "siteconfig" / "console_domains_hub.html"
    ccc_manager = (
        ROOT / "templates" / "siteconfig" / "console_domains_hub_control_plane.html"
    )
    outcomes_partial = (
        ROOT
        / "templates"
        / "siteconfig"
        / "partials"
        / "configuration_control_center_outcomes.html"
    )
    operator_partial = (
        ROOT
        / "templates"
        / "siteconfig"
        / "partials"
        / "configuration_control_center_operator_model.html"
    )
    registry_py = ROOT / "apps" / "siteconfig" / "control_outcome_center.py"

    for p in (ccc_tenant, ccc_manager, outcomes_partial, operator_partial, registry_py):
        if not p.is_file():
            errors.append(f"Missing required artifact: {p.relative_to(ROOT).as_posix()}")

    if errors:
        print("verify_phase4_control_plane_decision_console: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    # Template-level contract: both touched CCC templates include shared outcomes partial.
    include_snippet = '{% include "siteconfig/partials/configuration_control_center_outcomes.html" %}'
    for tpl in (ccc_tenant, ccc_manager):
        text = _read(tpl)
        rel = tpl.relative_to(ROOT).as_posix()
        if include_snippet not in text:
            errors.append(f"{rel} must include shared outcomes partial.")
        if 'data-page-archetype="decision-console"' not in text:
            errors.append(f"{rel} must declare decision-console archetype marker.")

    # Outcomes partial: must render outcome groups and source labels.
    outcomes_text = _read(outcomes_partial)
    if "{% if outcome_groups %}" not in outcomes_text:
        errors.append("configuration_control_center_outcomes.html missing outcome_groups guard.")
    if "group.links" not in outcomes_text:
        errors.append("configuration_control_center_outcomes.html missing grouped links rendering.")
    if "Sources" not in outcomes_text and "sources" not in outcomes_text:
        errors.append("configuration_control_center_outcomes.html missing source tracing display.")

    # Operator model partial: must render operator_control_model and stability labels.
    operator_text = _read(operator_partial)
    if "{% if operator_control_model %}" not in operator_text:
        errors.append("configuration_control_center_operator_model.html missing operator model guard.")
    if "step.primary.stability" not in operator_text:
        errors.append("configuration_control_center_operator_model.html missing stability signal rendering.")

    # Python registry/model contract.
    module = ast.parse(_read(registry_py))
    try:
        outcome_specs = _extract_literal_value(module, "OUTCOME_GROUP_SPECS")
        source_labels = _extract_literal_value(module, "SOURCE_LABELS")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"control_outcome_center.py literals unreadable: {exc}")
        outcome_specs = []
        source_labels = {}

    if isinstance(outcome_specs, list):
        if len(outcome_specs) < 9:
            errors.append(
                f"OUTCOME_GROUP_SPECS too small ({len(outcome_specs)}); expected >= 9 groups."
            )
    else:
        errors.append("OUTCOME_GROUP_SPECS must be a literal list.")

    if isinstance(source_labels, dict):
        for key in ("runtime", "pack", "policy", "entitlement", "tenant override"):
            if key not in source_labels:
                errors.append(f"SOURCE_LABELS missing required source key: {key!r}")
    else:
        errors.append("SOURCE_LABELS must be a literal dict.")

    registry_text = _read(registry_py)
    for required in (
        "source_tracing",
        "publish_rollback",
        "Runtime inspector",
        "Rollback (Control)",
        "Package rollout",
    ):
        if required not in registry_text:
            errors.append(f"control_outcome_center.py missing operator model token: {required}")

    if errors:
        print("verify_phase4_control_plane_decision_console: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        "verify_phase4_control_plane_decision_console: PASS "
        "(outcome groups + source tracing + publish/rollback affordances)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
