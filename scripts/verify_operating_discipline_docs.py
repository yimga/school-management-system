#!/usr/bin/env python3
"""
Verify §10.5 operating-discipline doc refs (RUNMYCAMPUS §10.5, BACKLOG §2e row 13).

Ensures every *_DOC constant in apps/dashboard/role_home_engine.py points to a
docs/ file that exists. Used in pre_deploy_gate so Phase I in-code doc refs
are enforced in CI.

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify role_home_engine *_DOC paths resolve under docs/."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (default: this repository root)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        base = _resolve_base(args.base)
    except ValueError as exc:
        print(f"[verify_operating_discipline_docs] {exc}", file=sys.stderr)
        return 1

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
    raise SystemExit(main(None))
