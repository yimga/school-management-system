#!/usr/bin/env python
"""Navigation simplification audit.

Parses control_plane_nav (manager surface) and reports group/item structure
with item counts per group. Surfaces oversize groups (>7 items, per cognitive
load research / v2.67 sidebar simplification target).

Writes docs/generated/navigation_simplification_audit.json.
"""
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAV_PATH = ROOT / "apps" / "schools" / "control_plane_nav.py"
OUT_PATH = ROOT / "docs" / "generated" / "navigation_simplification_audit.json"

OVERSIZE_THRESHOLD = 7  # Items beyond this stress short-term memory.


def extract_groups(tree: ast.Module) -> list[dict]:
    """Walk the AST of build_control_plane_nav and collect every add_group(name, [items]) call."""
    groups: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "add_group"):
            continue
        if len(node.args) < 2:
            continue
        name_arg = node.args[0]
        items_arg = node.args[1]
        if not isinstance(name_arg, ast.Constant) or not isinstance(items_arg, (ast.List, ast.Tuple)):
            continue
        group_name = name_arg.value
        item_count = 0
        item_ids: list[str] = []
        for el in items_arg.elts:
            if not isinstance(el, ast.Dict):
                continue
            item_count += 1
            for k, v in zip(el.keys, el.values):
                if isinstance(k, ast.Constant) and k.value == "id" and isinstance(v, ast.Constant):
                    item_ids.append(v.value)
        groups.append({
            "group": group_name,
            "item_count": item_count,
            "items": item_ids,
            "oversize": item_count > OVERSIZE_THRESHOLD,
        })
    return groups


def main() -> int:
    src = NAV_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    groups = extract_groups(tree)

    total_items = sum(g["item_count"] for g in groups)
    oversize_groups = [g for g in groups if g["oversize"]]
    biggest = max((g["item_count"] for g in groups), default=0)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generated_by": "scripts/audit_navigation_simplification.py",
                "source_file": str(NAV_PATH.relative_to(ROOT)).replace("\\", "/"),
                "oversize_threshold": OVERSIZE_THRESHOLD,
                "group_count": len(groups),
                "total_items": total_items,
                "biggest_group_size": biggest,
                "oversize_group_count": len(oversize_groups),
                "oversize_groups": [g["group"] for g in oversize_groups],
                "groups": groups,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"audit_navigation_simplification: {len(groups)} groups, {total_items} items")
    print(f"  biggest group:    {biggest} items")
    print(f"  oversize (>{OVERSIZE_THRESHOLD}): {len(oversize_groups)} group(s)")
    if oversize_groups:
        for g in oversize_groups:
            print(f"    - {g['group']}: {g['item_count']} items")
    print(f"  written:          {OUT_PATH.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
