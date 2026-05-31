#!/usr/bin/env python3
"""Bundle gate: platform + AI chrome + sovereign offline configurability cascades."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STEPS = (
    ("verify_platform_config_cascade.py", "PLATFORM_CONFIG_CASCADE"),
    ("verify_ai_chrome_no_hardcoding.py", "AI_CHROME_NO_HARDCODING"),
    ("verify_sovereign_offline_config_cascade.py", "SOVEREIGN_OFFLINE_CONFIG_CASCADE"),
    ("scan_hardcoded_client_fetch_paths.py", "HARDCODED_CLIENT_FETCH"),
    ("generate_platform_client_url_catalog.py --check", "PLATFORM_CLIENT_URL_CATALOG"),
)


def main() -> int:
    py = sys.executable
    failed: list[str] = []
    for script, label in STEPS:
        if " " in script:
            cmd = [py, str(ROOT / "scripts" / script.split()[0]), *script.split()[1:]]
        else:
            cmd = [py, str(ROOT / "scripts" / script)]
        if script.startswith("scan_"):
            cmd.append("--strict")
        print(f"--- {label} ---", flush=True)
        result = subprocess.run(cmd, cwd=ROOT, shell=False)
        if result.returncode != 0:
            failed.append(label)
    if failed:
        print(f"\nCLIENT_CONFIG_CASCADE_FAIL: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("CLIENT_CONFIG_CASCADE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
