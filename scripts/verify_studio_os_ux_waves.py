#!/usr/bin/env python3
"""Wave 6 gate: Studio OS UX waves 1–5 mechanical contracts (meta-runner)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WAVE_SCRIPTS = (
    "verify_studio_focus_layout.py",
    "verify_studio_embed_chrome.py",
    "verify_studio_workspace_layout.py",
    "verify_studio_control_inline.py",
    "verify_studio_nav_uniqueness.py",
    "verify_studio_command_deck.py",
    "verify_studio_os_playwright_scaffold.py",
    "verify_phase5_studio_os_conformance.py",
)


def main() -> int:
    failed: list[str] = []
    for name in WAVE_SCRIPTS:
        path = ROOT / "scripts" / name
        if not path.is_file():
            failed.append(f"missing {name}")
            continue
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip().splitlines()
            failed.append(f"{name}: {err[-1] if err else 'non-zero exit'}")
    if failed:
        print("verify_studio_os_ux_waves:", file=sys.stderr)
        for item in failed:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_studio_os_ux_waves: OK (waves 1–6 + phase5 conformance)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
