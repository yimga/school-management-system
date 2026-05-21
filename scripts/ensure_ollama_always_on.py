#!/usr/bin/env python3
"""
Ensure Ollama is reachable on this host (operator Lane 2).

Probes ``OLLAMA_BASE_URL`` / auto-discovery, optionally spawns ``ollama serve``,
then runs ``verify_ollama_live.py --invoke`` when ``--invoke`` is passed.

Usage:
  python scripts/ensure_ollama_always_on.py
  python scripts/ensure_ollama_always_on.py --invoke
  python scripts/ensure_ollama_always_on.py --strict

Set in ``.env.local`` (see ``.env.example``):
  OLLAMA_BASE_URL=http://127.0.0.1:11434
  OLLAMA_AUTO_START=1
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure Ollama daemon is up.")
    parser.add_argument("--invoke", action="store_true", help="Run one gateway invoke after probe.")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when Ollama stays unreachable.")
    args = parser.parse_args()

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ.setdefault("OLLAMA_AUTO_START", "1")

    import django

    django.setup()

    from services.ollama_runtime import ensure_ollama_reachable

    ensure_ollama_reachable(force_refresh=True)

    verify = [sys.executable, str(REPO_ROOT / "scripts" / "verify_ollama_live.py")]
    if args.strict:
        verify.append("--strict")
    if args.invoke:
        verify.append("--invoke")
    return subprocess.call(verify, cwd=str(REPO_ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
