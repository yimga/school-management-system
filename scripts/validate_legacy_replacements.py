#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate documented legacy → replacement behavior (LEGACY_PATH_INVENTORY §4).

Runs focused pytest modules: siteconfig Studio redirects, super admin bridges,
outcome center resolution, platform-admin bridge completeness.
Exit code 0 only if all pass.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TARGETS = [
    "apps/studio_os/tests/test_phase_05_legacy_redirects.py",
    "apps/schools/tests/test_super_config_migration_urls.py",
    "apps/siteconfig/tests/test_control_outcome_center.py",
    "apps/schools/tests/test_platform_admin_bridge_completeness.py",
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "-q", "--quiet", action="store_true", help="pytest -q"
    )
    args = p.parse_args()
    cmd = [sys.executable, "-m", "pytest"]
    if args.quiet:
        cmd.append("-q")
    cmd.extend(DEFAULT_TARGETS)
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
