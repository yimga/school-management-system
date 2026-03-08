#!/usr/bin/env python3
"""
Phase 12 CI: Flag SiteSettings.get_solo() and hardcoded region/currency/grading in tenant-facing code.
Use request.tenant_runtime or apps.platform_runtime.helpers (get_effective_flags, etc.) instead.
Usage: python scripts/lint_tenant_settings.py [--exit-zero]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Tenant-facing app labels (where SiteSettings.get_solo() should be replaced by runtime/helpers).
TENANT_APPS = (
    "apps/portal",
    "apps/evals",
    "apps/finance",
    "apps/dashboard",
    "apps/people",
    "apps/communication",
    "apps/accounts",
    "apps/reports",
    "apps/payroll",
    "apps/automation",
    "apps/api",
    "apps/observability",
    "apps/analytics",
    "apps/requests",
)

# Paths to skip entirely.
SKIP_DIRS = {"migrations", "node_modules", ".git", "__pycache__", "venv", ".venv", "scripts", "docs"}
SKIP_FILES = {"lint_tenant_settings.py"}

# Patterns: (regex, description)
SITESETTINGS_PATTERN = (re.compile(r"SiteSettings\.get_solo\s*\(\s*\)"), "SiteSettings.get_solo() (use runtime/helpers)")
HARDCODED_PATTERNS = [
    (re.compile(r"['\"]CMR['\"]|REGION_CODE\s*=\s*['\"]CMR['\"]"), "Hardcoded CMR (use env/registry)"),
    (re.compile(r"['\"]XAF['\"]|DEFAULT_CURRENCY\s*=\s*['\"]XAF['\"]"), "Hardcoded XAF (use env/registry)"),
    (re.compile(r"DEFAULT_GRADING_SCALE\s*=\s*['\"]0-20['\"]"), "Hardcoded 0-20 grading (use env/registry)"),
    (re.compile(r"['\"]Africa/Douala['\"]"), "Hardcoded Africa/Douala (use env/registry)"),
    (re.compile(r"DEFAULT_COUNTRY\s*=\s*['\"]"), "DEFAULT_COUNTRY hardcoded (use env/registry)"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Flag SiteSettings.get_solo() and hardcoded region/currency in tenant apps.")
    ap.add_argument("--exit-zero", action="store_true", help="Always exit 0 (report only).")
    ap.add_argument("--base", default=".", help="Base directory (default: .)")
    args = ap.parse_args()
    base = Path(args.base).resolve()
    if not base.is_dir():
        print(f"Not a directory: {base}", file=sys.stderr)
        return 2

    hits: list[tuple[str, int, str, str]] = []
    for py in base.rglob("*.py"):
        rel = py.relative_to(base)
        path_str = str(rel).replace("\\", "/")
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if py.name in SKIP_FILES:
            continue
        # Only tenant-facing apps for SiteSettings check; for hardcoded literals scan apps and config
        in_tenant_app = any(path_str.startswith(app) for app in TENANT_APPS)
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if in_tenant_app and SITESETTINGS_PATTERN[0].search(line):
                hits.append((path_str, i, line.strip()[:90], SITESETTINGS_PATTERN[1]))
            for pat, label in HARDCODED_PATTERNS:
                if pat.search(line) and "settings.py" not in path_str and "env.example" not in path_str:
                    hits.append((path_str, i, line.strip()[:90], label))
                    break

    if not hits:
        print("lint_tenant_settings: No SiteSettings.get_solo() or hardcoded region/currency in tenant paths.")
        return 0
    print("Phase 12 CI: Prefer request.tenant_runtime / platform_runtime.helpers (see SITESETTINGS_AUDIT.md):\n")
    for path, line_no, snippet, label in hits:
        print(f"  {path}:{line_no}  {label}")
        print(f"    {snippet}")
    print(f"\nTotal: {len(hits)} hit(s).")
    return 0 if args.exit_zero else 1


if __name__ == "__main__":
    sys.exit(main())
