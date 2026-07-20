#!/usr/bin/env python3
"""Strict real-host wrapper for the Django admin approval-canvas verifier.

The former harness soft-passed unreachable servers, used only 127.0.0.1,
targeted retired ``auth.User`` routes, and expected a simulated Preview toggle.
That could not prove which AdminSite host routing selected. This wrapper now
delegates to the strict Playwright matrix, which maps and asserts both real
manager and tenant hostnames.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "scripts" / "verify_django_admin_real_host_matrix.mjs"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--theme", choices=("light", "dark"), default="light")
    parser.add_argument("--scope", choices=("operator", "tenant", "both"), default="both")
    parser.add_argument("--suite", choices=("core", "specialized"), default="core")
    parser.add_argument("--only", default="")
    parser.add_argument("--models", default="")
    parser.add_argument("--port", type=int, default=8020)
    parser.add_argument("--screenshots", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("RMC_ADMIN_SESSIONID", "").strip():
        print("DJANGO_ADMIN_CANVAS_LIVE_FAIL")
        print("  - RMC_ADMIN_SESSIONID is required; soft-pass is intentionally disabled")
        return 2

    command = [
        "node",
        str(MATRIX),
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--theme",
        args.theme,
        "--scope",
        args.scope,
        "--suite",
        args.suite,
        "--port",
        str(args.port),
    ]
    if args.only:
        command.extend(("--only", args.only))
    if args.models:
        command.extend(("--models", args.models))
    if args.screenshots:
        command.append("--screenshots")

    completed = subprocess.run(command, cwd=ROOT, check=False)  # noqa: S603
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
