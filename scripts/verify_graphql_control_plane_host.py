#!/usr/bin/env python3
"""AWS pillar: GraphQL global school registry limited to manager host."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    text = (ROOT / "config" / "schema.py").read_text(encoding="utf-8")
    failures: list[str] = []

    if 'return host_kind == "manager"' not in text:
        failures.append("schema.py must require host_kind == manager")
    if re.search(r'return host_kind in \{"manager", "local", ""\}', text):
        failures.append("schema.py still allows loose host_kind set")

    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        print(f"verify_graphql_control_plane_host: {len(failures)} FAIL", file=sys.stderr)
        return 1
    print("verify_graphql_control_plane_host: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
