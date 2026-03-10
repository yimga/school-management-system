#!/usr/bin/env python3
"""
Block new app code from importing legacy siteconfig domain wrappers.

These wrappers still exist for cutover compatibility, but new code must import
from the bounded-context surfaces instead.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SKIP_PARTS = {"migrations", "__pycache__", "venv", ".venv", "node_modules", "tests"}
FORBIDDEN = (
    (re.compile(r"\bfrom\s+apps\.siteconfig\.models_brand\s+import\b"), "apps.brand_experience.models"),
    (re.compile(r"\bfrom\s+apps\.siteconfig\.models_runtime_blueprints\s+import\b"), "apps.runtime_blueprints.models"),
    (re.compile(r"\bfrom\s+apps\.siteconfig\.models_policies_rules\s+import\b"), "apps.policies_rules.models"),
    (re.compile(r"\bfrom\s+apps\.siteconfig\.models_global_registries\s+import\b"), "apps.global_registries.models"),
    (re.compile(r"\bfrom\s+apps\.siteconfig\.models_integrations_marketplace\s+import\b"), "apps.integrations_marketplace.models"),
    (re.compile(r"\bfrom\s+apps\.siteconfig\.models_plans_entitlements\s+import\b"), "apps.plans_entitlements.models"),
)


def main() -> int:
    violations: list[tuple[str, int, str]] = []
    for root_name in ("apps", "config"):
        root = BASE / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            rel = path.relative_to(BASE).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_no, line in enumerate(text.splitlines(), start=1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                for pattern, replacement in FORBIDDEN:
                    if pattern.search(line):
                        violations.append((rel, line_no, replacement))
                        break
    if not violations:
        print("lint_siteconfig_legacy_imports: no legacy siteconfig domain wrapper imports found.")
        return 0
    print("lint_siteconfig_legacy_imports: legacy siteconfig wrapper imports must move to bounded-context surfaces:\n", file=sys.stderr)
    for rel, line_no, replacement in violations:
        print(f"  {rel}:{line_no} -> import from {replacement}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
