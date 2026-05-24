#!/usr/bin/env python3
"""Run GEOS-99 + unified AI + Lane 2 completion audit (single orchestrator)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(label: str, cmd: list[str], *, optional: bool = False) -> bool:
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True)
    ok = proc.returncode == 0
    status = "OK" if ok else ("SKIP" if optional else "FAIL")
    print(f"[{status}] {label}")
    return ok or optional


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--school-slug", default="demo-school")
    parser.add_argument(
        "--skip-pilot-record",
        action="store_true",
        help="Skip manage.py record_geos_internal_core_loop (already recorded).",
    )
    parser.add_argument(
        "--skip-email-capture",
        action="store_true",
        help="Skip welcome .eml capture.",
    )
    args = parser.parse_args()
    py = sys.executable
    failed = 0

    steps = [
        (
            "Lane 2 scaffold",
            [py, str(ROOT / "scripts/verify_geos_lane2_scaffold.py")],
            False,
        ),
        (
            "Unified AI assistant",
            [py, str(ROOT / "scripts/verify_unified_ai_assistant.py")],
            False,
        ),
        (
            "Unified AI Lane 2 readiness",
            [py, str(ROOT / "scripts/verify_unified_ai_lane2_readiness.py")],
            False,
        ),
        (
            "Help center tiers",
            [py, str(ROOT / "scripts/verify_help_center_tiers.py")],
            False,
        ),
    ]
    if not args.skip_email_capture:
        steps.append(
            (
                "Email welcome evidence",
                [py, str(ROOT / "scripts/capture_geos_email_welcome_evidence.py")],
                True,
            )
        )
    if not args.skip_pilot_record:
        steps.append(
            (
                "Internal pilot core loop",
                [
                    py,
                    str(ROOT / "manage.py"),
                    "record_geos_internal_core_loop",
                    f"--school-slug={args.school_slug}",
                ],
                True,
            )
        )
    steps.extend(
        [
            (
                "Sync evidence to register",
                [py, str(ROOT / "scripts/sync_geos_evidence_to_register.py"), "--write"],
                False,
            ),
            (
                "GEOS matrix (repo)",
                [
                    py,
                    str(ROOT / "scripts/verify_greatest_education_os_matrix.py"),
                    "--write",
                ],
                False,
            ),
            (
                "GEOS matrix (composite 99+)",
                [
                    py,
                    str(ROOT / "scripts/verify_greatest_education_os_matrix.py"),
                    "--require-composite-99",
                ],
                False,
            ),
            (
                "npm verify:geos-99 bundle",
                ["npm", "run", "verify:geos-99"],
                True,
            ),
            (
                "npm verify:geos-ai-unified",
                ["npm", "run", "verify:geos-ai-unified"],
                True,
            ),
        ]
    )

    for label, cmd, optional in steps:
        if not _run(label, cmd, optional=optional):
            failed += 1

    if failed:
        print(f"run_geos_full_audit: FAIL ({failed} step(s))", file=sys.stderr)
        return 1
    print("run_geos_full_audit: GEOS_FULL_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
