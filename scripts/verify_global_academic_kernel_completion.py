#!/usr/bin/env python3
"""Completion audit for global academic OS kernel (batches 1585–1586)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "generated" / "global_academic_kernel_completion_audit.json"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

_REQUIRED_FILES = (
    "apps/governance/academic_pack_bridge.py",
    "apps/academics/academic_structure.py",
    "apps/academics/structure_provisioning.py",
    "apps/policies/grading_nuance_templates.py",
    "scripts/verify_global_academic_kernel_assumptions.py",
    "scripts/verify_grading_scale_registry_coverage.py",
)

_OPTIONAL_GAPS = (
    "onboarding_step_catalog: no dedicated academic-structure-confirm step",
    "scheduling_solver: shift dimension not propagated to CP-SAT solver",
    "verify_global_academic_kernel_assumptions: no AST school.settings grading scan",
    "tier1_burndown: dissection ledger skeleton→verified is operator cadence",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    import django

    django.setup()

    from django.apps import apps
    from django.urls import NoReverseMatch, reverse

    failures: list[str] = []
    checks: list[dict[str, str]] = []

    for rel in _REQUIRED_FILES:
        path = REPO / rel
        ok = path.is_file()
        checks.append({"id": rel, "status": "PASS" if ok else "FAIL"})
        if not ok:
            failures.append(f"missing file: {rel}")

    url_names = (
        "api_v1:runtime-structural-options",
        "api_v1:runtime-structural-options-initialize",
        "api_v1:runtime-grading-matrix",
    )
    for name in url_names:
        try:
            reverse(name)
            checks.append({"id": f"url:{name}", "status": "PASS"})
        except NoReverseMatch:
            checks.append({"id": f"url:{name}", "status": "FAIL"})
            failures.append(f"url not registered: {name}")

    for label in ("academics.AcademicStructureNode", "academics.InstructionShift"):
        app_label, model_name = label.split(".", 1)
        try:
            apps.get_model(app_label, model_name)
            checks.append({"id": label, "status": "PASS"})
        except LookupError:
            checks.append({"id": label, "status": "FAIL"})
            failures.append(f"model missing: {label}")

    event_types = {
        c[0]
        for c in apps.get_model("schools", "SchoolProvisioningEvent").EventType.choices
    }
    if "ACADEMIC_STRUCTURE_READY" not in event_types:
        failures.append("SchoolProvisioningEvent.EventType missing ACADEMIC_STRUCTURE_READY")
        checks.append({"id": "provisioning_event_type", "status": "FAIL"})
    else:
        checks.append({"id": "provisioning_event_type", "status": "PASS"})

    payload = {
        "verdict": "GLOBAL_ACADEMIC_KERNEL_COMPLETION_PASS"
        if not failures
        else "GLOBAL_ACADEMIC_KERNEL_COMPLETION_FAIL",
        "finding_count": len(failures),
        "checks": checks,
        "findings": failures,
        "documented_honest_gaps": list(_OPTIONAL_GAPS),
    }
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if failures and args.strict:
        print(f"verify_global_academic_kernel_completion: FAIL ({len(failures)})", file=sys.stderr)
        for line in failures[:20]:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"verify_global_academic_kernel_completion: {payload['verdict']}")
    print(f"  checks={len(checks)} documented_gaps={len(_OPTIONAL_GAPS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
