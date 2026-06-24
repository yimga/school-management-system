from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(ROOT))

    import django

    django.setup()

    failures: list[str] = []
    mod_path = ROOT / "apps" / "platform_runtime" / "tenant_operational_lifecycle.py"
    text = mod_path.read_text(encoding="utf-8")
    tree = ast.parse(text)

    from apps.platform_runtime.tenant_operational_lifecycle import (
        ALL_OPERATIONAL_STATES,
        REQUIRED_OPERATIONAL_STATES,
        resolve_operational_lifecycle_state,
        validate_operational_transition,
    )

    if tuple(REQUIRED_OPERATIONAL_STATES) != tuple(ALL_OPERATIONAL_STATES):
        failures.append("REQUIRED_OPERATIONAL_STATES must match ALL_OPERATIONAL_STATES")

    if "def resolve_operational_lifecycle_state" not in text:
        failures.append("missing resolve_operational_lifecycle_state")

    # Every required state must appear as a string literal in the resolver module.
    for state in REQUIRED_OPERATIONAL_STATES:
        if f'"{state}"' not in text and f"'{state}'" not in text:
            failures.append(f"operational state not referenced in module: {state}")

    # Transition validator must be callable.
    if not validate_operational_transition("provisioning", "country_setup"):
        failures.append("validate_operational_transition rejected valid edge")

    # Resolver must handle None school → conception.
    none_result = resolve_operational_lifecycle_state(None)
    if none_result.get("state") != "conception":
        failures.append("None school must resolve to conception")

    # Module must define ALLOWED_OPERATIONAL_TRANSITIONS.
    has_transitions = any(
        (
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "ALLOWED_OPERATIONAL_TRANSITIONS"
                for t in node.targets
            )
        )
        or (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "ALLOWED_OPERATIONAL_TRANSITIONS"
        )
        for node in tree.body
    )
    if not has_transitions:
        failures.append("missing ALLOWED_OPERATIONAL_TRANSITIONS")

    if failures:
        print("verify_operational_lifecycle_fsm_coverage: FAIL")
        for f in failures:
            print(f"- {f}")
        return 1

    print(
        "verify_operational_lifecycle_fsm_coverage: "
        "OPERATIONAL_LIFECYCLE_FSM_COVERAGE_PASS"
    )
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
