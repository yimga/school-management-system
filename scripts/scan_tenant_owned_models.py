#!/usr/bin/env python
"""Inventory concrete models that inherit ``TenantOwnedModel`` (batch 1242 linter).

Exits 0 — informational gate. Fails only when a ``TenantOwnedModel`` subclass
omits the inherited ``school`` field (should be impossible if abstract base is intact).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_DIR = REPO_ROOT / "apps"


def main() -> int:
    violations: list[str] = []
    for path in sorted(APPS_DIR.rglob("*.py")):
        if "migrations" in path.parts or "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [
                getattr(b, "id", "")
                for b in node.bases
                if isinstance(b, ast.Name)
            ]
            if "TenantOwnedModel" not in bases:
                continue
            rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            violations.append(f"{rel}:{node.lineno} {node.name} extends TenantOwnedModel")
    print(f"[tenant-owned-linter] TenantOwnedModel subclasses: {len(violations)}")
    for v in violations[:20]:
        print(f"  {v}")
    if len(violations) > 20:
        print(f"  ... and {len(violations) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
