#!/usr/bin/env python3
"""Batch 1500 validation audit — help center + KB corpus + complete sidebar + back-to-top."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GATES: tuple[tuple[str, list[str]], ...] = (
    (
        "kb-corpus",
        [
            "scripts/verify_workflow_kb_corpus.py",
            "scripts/verify_workflow_kb_corpus_quality.py",
            "scripts/verify_workflow_kb_editorial.py",
        ],
    ),
    (
        "help-center",
        [
            "scripts/verify_help_center_tiers.py",
            "scripts/verify_admin_super_help_nav_bridge.py",
            "scripts/verify_help_auto_draft_posture.py",
        ],
    ),
    (
        "nav-chrome",
        [
            "scripts/verify_manager_nav_convergence.py",
            "scripts/verify_platform_back_to_top.py",
            "scripts/verify_page_fold_standards.py",
        ],
    ),
    (
        "interaction",
        [
            "scripts/verify_interaction_integrity_completion.py",
            "scripts/scan_operator_shell_dead_hrefs.py",
            "--strict",
        ],
    ),
)


def main() -> int:
    failed: list[str] = []
    passed = 0
    for family, cmd in GATES:
        proc = subprocess.run(
            [sys.executable, *[str(ROOT / c) for c in cmd]],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        label = " ".join(Path(c).name for c in cmd if not c.startswith("-"))
        if proc.returncode != 0:
            failed.append(f"{family}: {label}")
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
            for line in tail:
                print(line, file=sys.stderr)
        else:
            passed += 1
            last = (proc.stdout + proc.stderr).strip().splitlines()
            if last:
                print(last[-1])

    if failed:
        print(f"verify_help_nav_finish_audit: FAIL ({len(failed)} families)", file=sys.stderr)
        for line in failed:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(
        f"verify_help_nav_finish_audit: HELP_NAV_FINISH_AUDIT_PASS "
        f"({passed}/{len(GATES)} families)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
