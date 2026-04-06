#!/usr/bin/env python3
"""
Phase B Batch 3 burn-in: fail on direct SiteSettings ORM usage for FK columns
removed in siteconfig.0163 (theme packs + default report styles → PlatformGlobalBranding).

Use apply_theme_experience_state(), PlatformGlobalBranding, or resolvers — not
SiteSettings.save(update_fields=[...]) / SiteSettings.objects.create(..., theme_pack=...).

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT
APPS = ROOT / "apps"

SKIP_DIR_NAMES = frozenset({"migrations", "__pycache__", ".venv", "venv"})

# Historical migration code must keep old column names.
ALLOWLIST_REL_PATHS = frozenset(
    {
        str(Path("apps/siteconfig/migrations/0076_normalize_themepack_defaults_and_constraint.py")),
    }
)

# Direct attribute assign on the usual SiteSettings variable name (tests / views).
_ASSIGN_RE = re.compile(
    r"\bsite\.(theme_pack|admin_theme_pack|teacher_theme_pack|parent_theme_pack|default_term_report_style|default_annual_report_style)\s*="
)

_REMOVED_UPDATE_FIELD_NAMES = (
    "theme_pack",
    "admin_theme_pack",
    "teacher_theme_pack",
    "parent_theme_pack",
    "default_term_report_style",
    "default_annual_report_style",
)


def _site_save_with_removed_fk(line: str) -> bool:
    """Only flag site.save(..., update_fields=[...]) on one line (PlatformGlobalBranding uses pgb.save)."""
    if "site.save" not in line or "update_fields" not in line:
        return False
    return any(name in line for name in _REMOVED_UPDATE_FIELD_NAMES)

_CREATE_RE = re.compile(
    r"SiteSettings\.objects\.create\s*\([^\)]*"
    r"(theme_pack|admin_theme_pack|teacher_theme_pack|parent_theme_pack|default_term_report_style|default_annual_report_style)\s*="
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lint removed SiteSettings FK writes after Phase B Batch 3."
    )
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root to inspect (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"--base directory not found: {raw_base}")
    return base


def _configure_root(base: Path) -> None:
    global ROOT
    global APPS
    ROOT = base
    APPS = ROOT / "apps"


def _should_scan(path: Path) -> bool:
    if path.suffix != ".py":
        return False
    parts = set(path.parts)
    if parts & SKIP_DIR_NAMES:
        return False
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        return False
    if rel in ALLOWLIST_REL_PATHS:
        return False
    return rel.startswith("apps/")


def main(argv: list[str] | None = None) -> int:
    try:
        _configure_root(_resolve_base(parse_args(argv).base))
    except ValueError as exc:
        print("lint_phase_b_batch3_sitesettings_fk_writes FAILED:", file=sys.stderr)
        print(f"  {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    for path in sorted(APPS.rglob("*.py")):
        if not _should_scan(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _ASSIGN_RE.search(line):
                errors.append(f"{rel}:{lineno}: Batch3: assign removed SiteSettings FK — use PGB or apply_theme_experience_state")
            if _site_save_with_removed_fk(line):
                errors.append(f"{rel}:{lineno}: Batch3: site.save(update_fields=...) references removed SiteSettings FK")
            if _CREATE_RE.search(line):
                errors.append(f"{rel}:{lineno}: Batch3: SiteSettings.objects.create(...) passes removed FK kwarg")

    if errors:
        print("lint_phase_b_batch3_sitesettings_fk_writes FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    print("lint_phase_b_batch3_sitesettings_fk_writes OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
