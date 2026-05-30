#!/usr/bin/env python3
"""Studio OS 10X completion gate.

Loads `docs/generated/studio_os_10x_completion_register.json` and asserts every
item has status `DONE` or `EXTERNAL_BLOCKED`. In `--strict` mode any
`NOT_DONE` or `IN_PROGRESS` item fails the build.

Mirrors `scripts/verify_global_governance_plan_completion.py` so the CI wiring
pattern is identical.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTER_PATH = REPO / "docs" / "generated" / "studio_os_10x_completion_register.json"

ALLOWED_PASS = {"DONE", "EXTERNAL_BLOCKED"}
ALLOWED_LENIENT = ALLOWED_PASS | {"IN_PROGRESS"}


def _load_register() -> dict:
    if not REGISTER_PATH.is_file():
        print(f"studio_os_10x_register_missing: {REGISTER_PATH}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"studio_os_10x_register_unparseable: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail on IN_PROGRESS / NOT_DONE (default fails only on NOT_DONE)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable verdict to stdout")
    args = parser.parse_args()

    register = _load_register()
    items = register.get("items") or []
    if not items:
        print("studio_os_10x_register_empty", file=sys.stderr)
        return 1

    allowed = ALLOWED_PASS if args.strict else ALLOWED_LENIENT
    failures: list[dict] = []
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "NOT_DONE")
        counts[status] = counts.get(status, 0) + 1
        if status not in allowed:
            failures.append({
                "id": item.get("id"),
                "title": item.get("title"),
                "status": status,
                "wave": item.get("wave"),
                "pillar": item.get("pillar"),
            })

    verdict = "STUDIO_OS_10X_PASS" if not failures else "STUDIO_OS_10X_FAIL"
    payload = {
        "verdict": verdict,
        "strict": bool(args.strict),
        "total": len(items),
        "status_counts": counts,
        "failure_count": len(failures),
        "failures": failures[:25],
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        if failures:
            print(f"{verdict}: {len(failures)} item(s) not closed", file=sys.stderr)
            for row in failures[:25]:
                print(f"  - {row['id']} [{row['status']}] ({row['pillar']} W{row['wave']}): {row['title']}", file=sys.stderr)
            if len(failures) > 25:
                print(f"  ... and {len(failures) - 25} more", file=sys.stderr)
        else:
            print(f"{verdict}: {len(items)} items, counts={counts}")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
