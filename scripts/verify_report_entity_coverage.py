#!/usr/bin/env python3
"""Ensure operational reporting covers the entity catalog (and does not lie).

The product thesis is: named platform entities are reportable without a new
hand-written exporter. This gate fails when:

  1. ``seed_entity_catalog.CATALOG_ENTITIES`` has a code with no
     ``ReportableEntity`` row (runnable or explicit deny).
  2. ``adhoc_runner`` still has the dishonest CUSTOM → students[:1000] fallback.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "apps" / "metadata" / "management" / "commands" / "seed_entity_catalog.py"
REGISTRY = ROOT / "apps" / "reports" / "report_entity_registry.py"
RUNNER = ROOT / "apps" / "reports" / "adhoc_runner.py"

_DISHONEST_NEEDLES = (
    "minimal students list",
    "qs[:1000]",
    "qs = qs[:1000]",
)


def _catalog_codes(source: str) -> list[str]:
    tree = ast.parse(source)
    codes: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "CATALOG_ENTITIES" for t in node.targets
        ):
            continue
        if not isinstance(node.value, ast.List):
            continue
        for elt in node.value.elts:
            if isinstance(elt, ast.Tuple) and elt.elts:
                first = elt.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    codes.append(first.value)
    return codes


def _registry_codes(source: str) -> list[str]:
    tree = ast.parse(source)
    codes: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name != "ReportableEntity":
            continue
        for kw in node.keywords:
            if kw.arg == "code" and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, str):
                    codes.append(kw.value.value)
    return codes


def main() -> int:
    seed_src = SEED.read_text(encoding="utf-8")
    reg_src = REGISTRY.read_text(encoding="utf-8")
    run_src = RUNNER.read_text(encoding="utf-8")
    catalog = _catalog_codes(seed_src)
    registry = _registry_codes(reg_src)
    missing = [c for c in catalog if c not in registry]
    dishonest = [n for n in _DISHONEST_NEEDLES if n in run_src]
    if "queryset_for_code" not in run_src:
        print("REPORT_ENTITY_COVERAGE_FAIL: adhoc_runner does not call queryset_for_code")
        return 1
    if not catalog:
        print("REPORT_ENTITY_COVERAGE_FAIL: no CATALOG_ENTITIES codes parsed")
        return 1
    if missing or dishonest:
        print("REPORT_ENTITY_COVERAGE_FAIL")
        if missing:
            print(f"  catalog_codes_unregistered: {missing}")
        if dishonest:
            print(f"  dishonest_fallback: {dishonest}")
        return 1
    print("REPORT_ENTITY_COVERAGE_PASS")
    print(f"  catalog_codes: {len(catalog)}")
    print(f"  registry_codes: {len(registry)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
