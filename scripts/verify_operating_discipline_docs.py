#!/usr/bin/env python3
"""
Verify §10.5 operating-discipline doc refs (RUNMYCAMPUS §10.5, BACKLOG §2e row 13).

Ensures every *_DOC constant in apps/dashboard/role_home_engine.py points to a
docs/ file that exists. Used in pre_deploy_gate so Phase I in-code doc refs
are enforced in CI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    base = Path(__file__).resolve().parent.parent
    engine = base / "apps" / "dashboard" / "role_home_engine.py"
    if not engine.is_file():
        print(f"[verify_operating_discipline_docs] Missing: {engine}", file=sys.stderr)
        return 1

    text = engine.read_text(encoding="utf-8", errors="replace")
    # Match *_DOC = "docs/...something..."
    pattern = re.compile(r'[A-Z][A-Z0-9_]*_DOC\s*=\s*"(docs/[^"]+)"')
    refs = pattern.findall(text)
    if not refs:
        print(
            "[verify_operating_discipline_docs] No *_DOC constants found in role_home_engine.py",
            file=sys.stderr,
        )
        return 1

    missing: list[str] = []
    for doc_path in refs:
        full = (base / doc_path).resolve()
        if not full.is_file():
            missing.append(doc_path)

    if missing:
        for p in missing:
            print(
                f"[verify_operating_discipline_docs] Missing doc: {p}", file=sys.stderr
            )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
