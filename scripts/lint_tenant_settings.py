#!/usr/bin/env python3
"""
Phase 12 CI: Flag SiteSettings.get_solo() and hardcoded region/currency/grading in tenant-facing code.
Use request.tenant_runtime or apps.platform_runtime.helpers (get_effective_flags, etc.) instead.

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

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
    "apps/student360",
    "apps/compliance",
    "apps/academics",
    "apps/studio_os",
)

# Paths to skip entirely.
SKIP_DIRS = {
    "migrations",
    "node_modules",
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "scripts",
    "docs",
}
SKIP_FILES = {"lint_tenant_settings.py"}

# Paths where SiteSettings.get_solo() is allowed (singleton definition + canonical helpers only).
# Management commands are not exempt: under apps/finance/ and apps/reports/ they live in tenant
# app trees and must use get_platform_site_settings_record / get_effective_site_settings.
# siteconfig/platform_runtime management packages are outside TENANT_APPS and are not scanned
# for get_solo violations; they still must not call SiteSettings.get_solo() in new code.
ALLOWED_GET_SOLO_PREFIXES = (
    "apps/siteconfig/models.py",
    "apps/platform_runtime/helpers.py",
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
    "apps/api/br_northstar_views.py",  # BR-09 legacy SIS connector config persisted on school.settings
    "apps/api/oneroster_roster_webhook.py",  # Incoming webhook: lookup by school_id; roster_webhook_secret on school.settings
    "apps/compliance/attendance_region_packs.py",
    "apps/compliance/enrollment_region_packs.py",
    "apps/communication/management/commands/purge_thread_message_retention.py",
)

# Patterns: (regex, description)
SITESETTINGS_PATTERN = (
    re.compile(r"SiteSettings\.get_solo\s*\(\s*\)"),
    "SiteSettings.get_solo() (use runtime/helpers)",
)
SITESETTINGS_LOAD_PATTERN = (
    re.compile(r"SiteSettings\.load\s*\(\s*\)"),
    "SiteSettings.load() (use runtime/helpers)",
)
SCHOOL_SETTINGS_PATTERN = (
    re.compile(r"\bschool\.settings\b"),
    "school.settings (use request.tenant_runtime or get_effective_*)",
)
SCHOOL_FEATURES_PATTERN = (
    re.compile(r"\bschool\.features\b"),
    "school.features (use request.tenant_runtime or get_effective_*)",
)
# Phase 5: direct SiteSettings ORM queries in tenant-facing apps (use platform_runtime.helpers).
SITESETTINGS_OBJECTS_PATTERN = (
    re.compile(r"SiteSettings\.objects\.(get|filter|first|all|create|update|get_or_create)\s*\("),
    "SiteSettings.objects.* (use get_platform_site_settings_record / runtime helpers in tenant code)",
)
HARDCODED_PATTERNS = [
    (
        re.compile(r"['\"]CMR['\"]|REGION_CODE\s*=\s*['\"]CMR['\"]"),
        "Hardcoded CMR (use env/registry)",
    ),
    (
        re.compile(r"['\"]XAF['\"]|DEFAULT_CURRENCY\s*=\s*['\"]XAF['\"]"),
        "Hardcoded XAF (use env/registry)",
    ),
    (
        re.compile(r"DEFAULT_GRADING_SCALE\s*=\s*['\"]0-20['\"]"),
        "Hardcoded 0-20 grading (use env/registry)",
    ),
    (
        re.compile(r"['\"]Africa/Douala['\"]"),
        "Hardcoded Africa/Douala (use env/registry)",
    ),
    (
        re.compile(r"DEFAULT_COUNTRY\s*=\s*['\"]"),
        "DEFAULT_COUNTRY hardcoded (use env/registry)",
    ),
    (
        re.compile(r"['\"]gilead-school['\"]|['\"]gilead_school['\"]"),
        "Hardcoded tenant slug (use DEFAULT_TENANT_SLUG or config)",
    ),
]


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


@lru_cache(maxsize=None)
def _tracked_file_relpaths(root: Path) -> frozenset[str] | None:
    """Prefer tracked files so local scratch trees do not create false positives."""
    if not (root / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false", "ls-files", "-z"],
            cwd=str(root),
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    relpaths: set[str] = set()
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            relpaths.add(Path(raw.decode("utf-8")).as_posix())
        except UnicodeDecodeError:
            continue
    return frozenset(relpaths)


def _iter_python_files(base: Path):
    tracked = _tracked_file_relpaths(base)
    if tracked is not None:
        for rel in sorted(tracked):
            if not rel.endswith(".py"):
                continue
            py = base / Path(rel)
            if py.is_file():
                yield py
        return
    yield from base.rglob("*.py")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Flag SiteSettings.get_solo() and hardcoded region/currency in tenant apps."
    )
    ap.add_argument(
        "--exit-zero", action="store_true", help="Always exit 0 (report only)."
    )
    ap.add_argument(
        "--check-get-solo-only",
        action="store_true",
        help="Only check get_solo(); ignore hardcoded (for CI).",
    )
    ap.add_argument(
        "--check-school-settings-features",
        action="store_true",
        help="Flag direct school.settings/school.features in tenant apps (use runtime).",
    )
    ap.add_argument(
        "--check-sitesettings-orm-in-tenant-apps",
        action="store_true",
        help="Flag SiteSettings.objects.* in tenant-facing app trees (Phase 5).",
    )
    ap.add_argument(
        "--report-allowlisted",
        action="store_true",
        help="Report get_solo() in allowlisted paths only (migration backlog for path to 10).",
    )
    ap.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (defaults to this repository root).",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        base = _resolve_base(args.base)
    except ValueError as exc:
        print(f"lint_tenant_settings: {exc}", file=sys.stderr)
        return 1

    hits: list[tuple[str, int, str, str]] = []
    for py in _iter_python_files(base):
        rel = py.relative_to(base)
        path_str = str(rel).replace("\\", "/")
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if py.name in SKIP_FILES:
            continue
        # Skip test files (tests may seed SiteSettings for fixtures).
        if (
            "/tests/" in path_str
            or path_str.startswith("apps/")
            and "/test_" in path_str
            or rel.name.startswith("test_")
        ):
            continue
        # Only tenant-facing apps for SiteSettings check; for hardcoded literals scan apps and config
        in_tenant_app = any(path_str.startswith(app) for app in TENANT_APPS)
        allowed_for_get_solo = any(
            path_str.startswith(p) for p in ALLOWED_GET_SOLO_PREFIXES
        )
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        allowed_for_school_settings = any(
            path_str.startswith(p) for p in ALLOWED_SCHOOL_SETTINGS_FEATURES_PREFIXES
        )
        for i, line in enumerate(text.splitlines(), 1):
            if getattr(args, "check_sitesettings_orm_in_tenant_apps", False):
                if in_tenant_app and SITESETTINGS_OBJECTS_PATTERN[0].search(line):
                    hits.append(
                        (path_str, i, line.strip()[:90], SITESETTINGS_OBJECTS_PATTERN[1])
                    )
                continue
            if (
                in_tenant_app
                and not allowed_for_get_solo
                and SITESETTINGS_PATTERN[0].search(line)
            ):
                hits.append((path_str, i, line.strip()[:90], SITESETTINGS_PATTERN[1]))
            if (
                getattr(args, "check_school_settings_features", False)
                and in_tenant_app
                and not allowed_for_school_settings
            ):
                if SCHOOL_SETTINGS_PATTERN[0].search(line):
                    hits.append(
                        (path_str, i, line.strip()[:90], SCHOOL_SETTINGS_PATTERN[1])
                    )
                if SCHOOL_FEATURES_PATTERN[0].search(line):
                    hits.append(
                        (path_str, i, line.strip()[:90], SCHOOL_FEATURES_PATTERN[1])
                    )
            if not getattr(args, "check_get_solo_only", False) and not getattr(
                args, "check_school_settings_features", False
            ):
                for pat, label in HARDCODED_PATTERNS:
                    if (
                        pat.search(line)
                        and "settings.py" not in path_str
                        and "env.example" not in path_str
                    ):
                        hits.append((path_str, i, line.strip()[:90], label))
                        break

    get_solo_hits = [
        (p, ln, sn, lb) for p, ln, sn, lb in hits if "get_solo" in lb or "load()" in lb
    ]
    if getattr(args, "report_allowlisted", False):
        # Path to 10: report get_solo() only in ALLOWED_GET_SOLO_PREFIXES (migration backlog).
        allowlisted_hits: list[tuple[str, int, str, str]] = []
        for py in _iter_python_files(base):
            rel = py.relative_to(base)
            path_str = str(rel).replace("\\", "/")
            if not any(path_str.startswith(p) for p in ALLOWED_GET_SOLO_PREFIXES):
                continue
            if any(part in SKIP_DIRS for part in rel.parts) or py.name in SKIP_FILES:
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if SITESETTINGS_PATTERN[0].search(line):
                    allowlisted_hits.append(
                        (path_str, i, line.strip()[:90], SITESETTINGS_PATTERN[1])
                    )
                if SITESETTINGS_LOAD_PATTERN[0].search(line):
                    allowlisted_hits.append(
                        (path_str, i, line.strip()[:90], SITESETTINGS_LOAD_PATTERN[1])
                    )
        print(
            "get_solo() in allowlisted paths (path to 10 — migrate to runtime/helpers):"
        )
        for path, line_no, snippet, label in allowlisted_hits:
            print(f"  {path}:{line_no}")
        print(f"Total allowlisted: {len(allowlisted_hits)}")
        return 0
    if args.check_get_solo_only:
        hits = get_solo_hits
    elif getattr(args, "check_school_settings_features", False):
        hits = [
            (p, ln, sn, lb)
            for p, ln, sn, lb in hits
            if "school.settings" in lb or "school.features" in lb
        ]
    elif getattr(args, "check_sitesettings_orm_in_tenant_apps", False):
        hits = [
            (p, ln, sn, lb)
            for p, ln, sn, lb in hits
            if "SiteSettings.objects" in lb
        ]

    if not hits:
        msg = "lint_tenant_settings: No SiteSettings.get_solo() or hardcoded region/currency in tenant paths."
        if getattr(args, "check_school_settings_features", False):
            msg = "lint_tenant_settings: No direct school.settings/school.features reads in tenant apps."
        if getattr(args, "check_sitesettings_orm_in_tenant_apps", False):
            msg = "lint_tenant_settings: No SiteSettings.objects.* in tenant-facing app paths."
        print(msg)
        return 0
    print(
        "Phase 12 CI: Prefer request.tenant_runtime / platform_runtime.helpers (see SITESETTINGS_AUDIT.md):\n"
    )
    for path, line_no, snippet, label in hits:
        print(f"  {path}:{line_no}  {label}")
        safe_snippet = (
            (snippet or "").encode("ascii", errors="replace").decode("ascii")[:90]
        )
        print(f"    {safe_snippet}")
    print(f"\nTotal: {len(hits)} hit(s).")
    return 0 if args.exit_zero else 1


if __name__ == "__main__":
    raise SystemExit(main(None))
