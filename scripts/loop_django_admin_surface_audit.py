#!/usr/bin/env python3
"""Continuous Django admin surface leftover loop.

Run until PASS, or until --max-rounds. Agents should fix findings between
rounds; this script only audits (does not auto-edit templates).

Usage:
  python scripts/loop_django_admin_surface_audit.py
  python scripts/loop_django_admin_surface_audit.py --max-rounds 5
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-rounds", type=int, default=1, help="Audit rounds (default 1)")
    ap.add_argument("--with-canvas", action="store_true", help="Also run canvas contract")
    args = ap.parse_args()

    leftovers = _load(
        "audit_django_admin_surface_leftovers",
        ROOT / "scripts" / "audit_django_admin_surface_leftovers.py",
    )
    canvas = None
    if args.with_canvas:
        canvas = _load(
            "audit_django_admin_canvas_contract",
            ROOT / "scripts" / "audit_django_admin_canvas_contract.py",
        )

    last = 1
    for round_i in range(1, max(1, args.max_rounds) + 1):
        print(f"\n=== Django admin leftover loop round {round_i}/{args.max_rounds} ===")
        last = leftovers.main()
        if canvas is not None:
            c = canvas.main()
            if c != 0:
                last = c
        if last == 0:
            print(f"LOOP_CLEAR after round {round_i}")
            return 0
        print(f"LOOP_FINDINGS remain after round {round_i} (exit={last})")
        if round_i < args.max_rounds:
            print("Fix findings, then re-run; continuing next audit round…")
    print("LOOP_NOT_CLEAR — leftovers remain; keep fixing and re-run.")
    return last


if __name__ == "__main__":
    sys.exit(main())
