#!/usr/bin/env python3
"""Emit docs/generated/ollama_live_proof.json from verify_ollama_live."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "ollama_live_proof.json"


def main() -> int:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_ollama_live.py"), "--strict", "--invoke"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strict_exit_code": proc.returncode,
        "stdout": proc.stdout[-4000:] if proc.stdout else "",
        "stderr": proc.stderr[-2000:] if proc.stderr else "",
        "live_ollama_verified": proc.returncode == 0,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} live={payload['live_ollama_verified']}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
