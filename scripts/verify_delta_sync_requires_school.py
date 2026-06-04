#!/usr/bin/env python3
"""AWS pillar: delta sync API and service fail closed without tenant id."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    failures: list[str] = []

    api = (ROOT / "apps" / "api" / "sync_delta_api.py").read_text(encoding="utf-8")
    if "if school is None:" not in api or "Tenant context required" not in api:
        failures.append("sync_delta_api.py missing tenant context 403")
    if "user_may_operate_on_school" not in api:
        failures.append("sync_delta_api.py missing user_may_operate_on_school")

    svc = (ROOT / "apps" / "api" / "sync_services.py").read_text(encoding="utf-8")
    if "if not school_id:" not in svc:
        failures.append("sync_services.py missing fail-closed school_id guard")

    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        print(f"verify_delta_sync_requires_school: {len(failures)} FAIL", file=sys.stderr)
        return 1
    print("verify_delta_sync_requires_school: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
