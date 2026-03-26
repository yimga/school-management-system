#!/usr/bin/env python3
"""
Enforce a single ORM entry point for the platform SiteSettings singleton row.

Production code under apps/ must not use ``SiteSettings.objects.*`` except:
  - ``apps/siteconfig/models.py`` (SiteSettings model implementation, e.g. get_solo)
  - ``apps/platform_runtime/helpers.py`` (``get_platform_site_settings_record`` and related)

Skipped trees: migrations, tests, __pycache__, management/commands (ops/bootstrap).

Exit 0 = no violations; non-zero = fix or use get_platform_site_settings_record(create=...).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PATTERN = re.compile(r"SiteSettings\.objects\.")

SKIP_DIR_PARTS = frozenset(
    {
        "migrations",
        "tests",
        "__pycache__",
        "management",
    }
)


def _allowlist(apps_root: Path) -> frozenset[Path]:
    return frozenset(
        {
            (apps_root / "siteconfig" / "models.py").resolve(),
            (apps_root / "platform_runtime" / "helpers.py").resolve(),
        }
    )


def _iter_py_files(apps_root: Path):
    if not apps_root.is_dir():
        return
    for path in apps_root.rglob("*.py"):
        rel = path.relative_to(apps_root.parent)
        parts = set(rel.parts)
        if parts & SKIP_DIR_PARTS:
            continue
        if "commands" in rel.parts and "management" in rel.parts:
            continue
        yield path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        type=Path,
        default=None,
        help="Repository root (default: parent of scripts/)",
    )
    args = parser.parse_args()
    root = (args.base or Path(__file__).resolve().parent.parent).resolve()
    apps_root = root / "apps"
    allowlist = _allowlist(apps_root)

    violations: list[str] = []
    for path in _iter_py_files(apps_root):
        if path.resolve() in allowlist:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            violations.append(f"{path.relative_to(root)}: read error: {e}")
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if PATTERN.search(line):
                stripped = line.split("#", 1)[0].strip()
                if not stripped:
                    continue
                violations.append(
                    f"{path.relative_to(root)}:{line_no}: {stripped[:120]}"
                )

    if violations:
        print(
            "lint_sitesettings_orm_singleton: SiteSettings.objects.* outside allowlist:\n",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nUse apps.platform_runtime.helpers.get_platform_site_settings_record "
            "(or add code only in helpers.py / siteconfig/models.py).",
            file=sys.stderr,
        )
        return 1
    print("lint_sitesettings_orm_singleton: OK (only models.py + helpers.py use SiteSettings.objects).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
