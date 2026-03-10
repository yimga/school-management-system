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

# Paths where SiteSettings.get_solo() is allowed (platform-default layer, control-plane, or shims).
ALLOWED_GET_SOLO_PREFIXES = (
    "apps/siteconfig/models.py",
    "apps/platform_runtime/helpers.py",
    "apps/policies/resolver.py",
    "apps/siteconfig/management/",
    "apps/finance/management/",
    "apps/reports/management/",
)

# Paths where direct school.settings / school.features reads are allowed (canonical readers/writers only).
ALLOWED_SCHOOL_SETTINGS_FEATURES_PREFIXES = (
    "apps/siteconfig/tenant_config.py",
    "apps/policies/resolver.py",
    "apps/schools/models.py",
    "apps/siteconfig/models.py",
    "apps/siteconfig/system_morph.py",
    "apps/siteconfig/views.py",
    "apps/schools/signup_views.py",
    "apps/schools/tasks.py",
    "apps/schools/management/",
    "apps/siteconfig/management/",
    "apps/compliance/management/",
    "apps/evals/runtime_gradebook.py",  # Docstring only: tells callers to use runtime, not school.settings
)

# Patterns: (regex, description)
SITESETTINGS_PATTERN = (re.compile(r"SiteSettings\.get_solo\s*\(\s*\)"), "SiteSettings.get_solo() (use runtime/helpers)")
SCHOOL_SETTINGS_PATTERN = (re.compile(r"\bschool\.settings\b"), "school.settings (use request.tenant_runtime or get_effective_*)")
SCHOOL_FEATURES_PATTERN = (re.compile(r"\bschool\.features\b"), "school.features (use request.tenant_runtime or get_effective_*)")
HARDCODED_PATTERNS = [
    (re.compile(r"['\"]CMR['\"]|REGION_CODE\s*=\s*['\"]CMR['\"]"), "Hardcoded CMR (use env/registry)"),
    (re.compile(r"['\"]XAF['\"]|DEFAULT_CURRENCY\s*=\s*['\"]XAF['\"]"), "Hardcoded XAF (use env/registry)"),
    (re.compile(r"DEFAULT_GRADING_SCALE\s*=\s*['\"]0-20['\"]"), "Hardcoded 0-20 grading (use env/registry)"),
    (re.compile(r"['\"]Africa/Douala['\"]"), "Hardcoded Africa/Douala (use env/registry)"),
    (re.compile(r"DEFAULT_COUNTRY\s*=\s*['\"]"), "DEFAULT_COUNTRY hardcoded (use env/registry)"),
    (re.compile(r"['\"]gilead-school['\"]|['\"]gilead_school['\"]"), "Hardcoded tenant slug (use DEFAULT_TENANT_SLUG or config)"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Flag SiteSettings.get_solo() and hardcoded region/currency in tenant apps.")
    ap.add_argument("--exit-zero", action="store_true", help="Always exit 0 (report only).")
    ap.add_argument("--check-get-solo-only", action="store_true", help="Only check get_solo(); ignore hardcoded (for CI).")
    ap.add_argument("--check-school-settings-features", action="store_true", help="Flag direct school.settings/school.features in tenant apps (use runtime).")
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
        # Skip test files (tests may seed SiteSettings for fixtures).
        if "/tests/" in path_str or path_str.startswith("apps/") and "/test_" in path_str or rel.name.startswith("test_"):
            continue
        # Only tenant-facing apps for SiteSettings check; for hardcoded literals scan apps and config
        in_tenant_app = any(path_str.startswith(app) for app in TENANT_APPS)
        allowed_for_get_solo = any(path_str.startswith(p) for p in ALLOWED_GET_SOLO_PREFIXES)
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        allowed_for_school_settings = any(path_str.startswith(p) for p in ALLOWED_SCHOOL_SETTINGS_FEATURES_PREFIXES)
        for i, line in enumerate(text.splitlines(), 1):
            if in_tenant_app and not allowed_for_get_solo and SITESETTINGS_PATTERN[0].search(line):
                hits.append((path_str, i, line.strip()[:90], SITESETTINGS_PATTERN[1]))
            if getattr(args, "check_school_settings_features", False) and in_tenant_app and not allowed_for_school_settings:
                if SCHOOL_SETTINGS_PATTERN[0].search(line):
                    hits.append((path_str, i, line.strip()[:90], SCHOOL_SETTINGS_PATTERN[1]))
                if SCHOOL_FEATURES_PATTERN[0].search(line):
                    hits.append((path_str, i, line.strip()[:90], SCHOOL_FEATURES_PATTERN[1]))
            if not getattr(args, "check_get_solo_only", False) and not getattr(args, "check_school_settings_features", False):
                for pat, label in HARDCODED_PATTERNS:
                    if pat.search(line) and "settings.py" not in path_str and "env.example" not in path_str:
                        hits.append((path_str, i, line.strip()[:90], label))
                        break

    get_solo_hits = [(p, ln, sn, lb) for p, ln, sn, lb in hits if "get_solo" in lb]
    if args.check_get_solo_only:
        hits = get_solo_hits
    elif getattr(args, "check_school_settings_features", False):
        hits = [(p, ln, sn, lb) for p, ln, sn, lb in hits if "school.settings" in lb or "school.features" in lb]

    if not hits:
        msg = "lint_tenant_settings: No SiteSettings.get_solo() or hardcoded region/currency in tenant paths."
        if getattr(args, "check_school_settings_features", False):
            msg = "lint_tenant_settings: No direct school.settings/school.features reads in tenant apps."
        print(msg)
        return 0
    print("Phase 12 CI: Prefer request.tenant_runtime / platform_runtime.helpers (see SITESETTINGS_AUDIT.md):\n")
    for path, line_no, snippet, label in hits:
        print(f"  {path}:{line_no}  {label}")
        safe_snippet = (snippet or "").encode("ascii", errors="replace").decode("ascii")[:90]
        print(f"    {safe_snippet}")
    print(f"\nTotal: {len(hits)} hit(s).")
    return 0 if args.exit_zero else 1


if __name__ == "__main__":
    sys.exit(main())
