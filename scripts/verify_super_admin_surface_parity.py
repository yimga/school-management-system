#!/usr/bin/env python3
"""
Verify operator surface IA spine and super-first ↔ admin bridge pairs.

Writes docs/generated/super_admin_surface_matrix.json and exits non-zero on drift.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from apps.schools.super_admin_paired_surfaces import build_surface_parity_matrix  # noqa: E402

DEFAULT_JSON = REPO_ROOT / "docs" / "generated" / "super_admin_surface_matrix.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write docs/generated/super_admin_surface_matrix.json",
    )
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    matrix = build_surface_parity_matrix()
    ok = (
        bool(matrix.get("spine_ok"))
        and bool(matrix.get("pairs_ok"))
        and bool(matrix.get("bindings_ok"))
        and bool(matrix.get("browser_probes_ok"))
    )

    if args.write:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.json}")

    if not matrix["spine_ok"]:
        bad = [r for r in matrix["spine"] if not r["ok"]]
        print("FAIL: operator surface spine links broken:", file=sys.stderr)
        for row in bad:
            print(f"  - {row['url_name']}", file=sys.stderr)
    if not matrix["pairs_ok"]:
        bad = [r for r in matrix["super_first_pairs"] if not r["ok"]]
        print("FAIL: super-first paired surfaces broken:", file=sys.stderr)
        for row in bad:
            print(f"  - {row['slug']}: {row}", file=sys.stderr)
    if not matrix.get("bindings_ok"):
        bad = [r for r in matrix.get("super_view_bindings", []) if not r["ok"]]
        print("FAIL: super view bridge bindings broken:", file=sys.stderr)
        for row in bad:
            print(f"  - {row['super_url_name']}", file=sys.stderr)
    if not matrix.get("browser_probes_ok"):
        bad = [r for r in matrix.get("browser_probes", []) if not r["ok"]]
        print("FAIL: browser parity probes unresolved:", file=sys.stderr)
        for row in bad:
            print(f"  - {row['slug']}", file=sys.stderr)

    if ok:
        print(
            "OK: super/admin surface parity "
            f"({len(matrix['spine'])} spine, {len(matrix['super_first_pairs'])} pairs, "
            f"{len(matrix.get('super_view_bindings', []))} view bindings, "
            f"{len(matrix.get('browser_probes', []))} browser probes)"
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
