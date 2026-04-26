#!/usr/bin/env python3
"""Fail if typed ownership map JSON is missing, empty, or schema drift."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAP = REPO / "docs" / "generated" / "sitesettings_typed_ownership_map.json"


def main() -> int:
    if not MAP.is_file():
        print("verify_sitesettings_typed_ownership_map: FAIL — map missing", file=sys.stderr)
        print(f"  run: python scripts/generate_sitesettings_typed_ownership_map.py", file=sys.stderr)
        return 1
    data = json.loads(MAP.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        print("verify_sitesettings_typed_ownership_map: FAIL — schema_version", file=sys.stderr)
        return 1
    fields = data.get("fields")
    if not isinstance(fields, dict) or len(fields) < 10:
        print("verify_sitesettings_typed_ownership_map: FAIL — fields too small", file=sys.stderr)
        return 1
    if "maintenance_mode" not in fields:
        print("verify_sitesettings_typed_ownership_map: FAIL — expected key", file=sys.stderr)
        return 1
    print(
        "verify_sitesettings_typed_ownership_map: PASS",
        f"({len(fields)} fields)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
