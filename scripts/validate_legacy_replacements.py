#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate documented legacy → replacement behavior (LEGACY_PATH_INVENTORY §4).

Runs focused pytest modules: siteconfig Studio redirects, super admin bridges,
outcome center resolution, platform-admin bridge completeness.

Run: python scripts/validate_legacy_replacements.py [--base REPO_ROOT] [-q]

Exit code 0 only if all pass.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TARGETS = [
    "apps/studio_os/tests/test_phase_05_legacy_redirects.py",
    "apps/schools/tests/test_super_config_migration_urls.py",
    "apps/siteconfig/tests/test_control_outcome_center.py",
    "apps/schools/tests/test_platform_admin_bridge_completeness.py",
]


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root (default: directory containing this script's parent).",
    )
    p.add_argument(
        "-q", "--quiet", action="store_true", help="pytest -q"
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repo_root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"validate_legacy_replacements: {exc}", file=sys.stderr)
        return 1

    cmd = [sys.executable, "-m", "pytest"]
    if args.quiet:
        cmd.append("-q")
    cmd.extend(DEFAULT_TARGETS)
    return int(subprocess.call(cmd, cwd=repo_root))


if __name__ == "__main__":
    raise SystemExit(main(None))
