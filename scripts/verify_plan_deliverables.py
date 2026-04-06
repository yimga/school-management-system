#!/usr/bin/env python3
"""
Verify Platform Hardening plan deliverables: key docs and runbooks exist.
Exit 0 if all required paths exist; exit 1 otherwise.
Use in CI or locally to ensure runbook/command docs are present.

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Project root (parent of scripts/); may be overridden per-run via ``_configure_root``.
ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

REQUIRED_DOCS = [
    "PLAN_COMPLETION_STATUS.md",
    "MANAGEMENT_COMMANDS_INDEX.md",
    "RUNBOOKS_INDEX.md",
    "SITESETTINGS_GET_SOLO_ALLOWLIST.md",
    "SCHOOL_FIELD_RESPONSIBILITY_MAP.md",
    "SITECONFIG_DECOMPOSITION_PLAN.md",
    "MARKETING_SHELL_VIEWS.md",
    "CONTROL_PLANE_BOUNDARY_RULES.md",
    "MIGRATION_CLOUD_RUNBOOK.md",
    "ACTIVATION_FLOWS.md",
    "PLATFORM_APPS_PUBLIC_API.md",
    "POLICY_BLUEPRINT_SINGLE_PATH.md",
    "MULTI_TENANT_ISOLATION.md",
    "OBSERVABILITY_AND_HEALTH.md",
    "PERMISSION_MODEL_AND_SECURITY.md",
    "OPTIMIZATION_AND_BUDGETS.md",
    "REGISTRIES_AND_STRUCTURE.md",
    "MARKETING_EXECUTION.md",
    "CONTROL_PLANE_COMMAND_CENTER.md",
    "CSS_RATIONALIZATION.md",
    "SHELL_ARCHITECTURE_MATRIX.md",
    "PROVIDER_REGISTRY_GOVERNANCE.md",
    "MODEL_TO_CANONICAL_ACTIONS_CHECKLIST.md",
    "GILEAD_RESIDUE.md",
]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify platform hardening plan deliverable docs."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _configure_root(base: Path) -> None:
    global ROOT, DOCS
    ROOT = base
    DOCS = ROOT / "docs"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _configure_root(_resolve_base(args.base))
    except ValueError as exc:
        print(f"verify_plan_deliverables: {exc}", file=sys.stderr)
        return 1

    missing = []
    for name in REQUIRED_DOCS:
        path = DOCS / name
        if not path.is_file():
            missing.append(str(path.relative_to(ROOT)))
    if missing:
        print("Missing plan deliverable docs:", file=sys.stderr)
        for m in sorted(missing):
            print("  -", m, file=sys.stderr)
        return 1
    print("All required plan deliverable docs present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
