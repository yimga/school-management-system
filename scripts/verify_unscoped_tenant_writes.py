#!/usr/bin/env python
"""Pre-deploy sweep for batch-1242 MEDIUM paths (deterministic file checks)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CHECKS = {
    "apps/evals/tasks.py": ("rls_school", "rls_bypass", "_requires_explicit_rls_context"),
    "apps/finance/signals.py": (
        "rls_school",
        "rls_bypass",
        "_run_with_optional_school_rls",
        "_requires_explicit_rls_context",
    ),
}


def main() -> int:
    failed = []
    for rel, needles in CHECKS.items():
        path = REPO_ROOT / rel
        text = path.read_text(encoding="utf-8")
        if not any(n in text for n in needles):
            failed.append(rel)
    if failed:
        print("[unscoped-write-sweep] missing RLS helpers in:", ", ".join(failed))
        return 1
    print("[unscoped-write-sweep] OK — evals/tasks + finance/signals RLS helpers present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
