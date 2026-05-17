#!/usr/bin/env python3
"""Parse k6 summary JSON (stdout) into docs/generated/k6_baseline_last_run.json."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "generated" / "k6_baseline_last_run.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--summary",
        type=Path,
        help="k6 --summary-export path (JSON). If omitted, writes a pending stub.",
    )
    parser.add_argument("--base-url", default="")
    args = parser.parse_args()

    payload: dict = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url or None,
        "status": "pending",
        "thresholds": {},
        "metrics": {},
    }

    if args.summary and args.summary.is_file():
        try:
            raw = json.loads(args.summary.read_text(encoding="utf-8"))
            payload["status"] = "recorded"
            payload["metrics"] = raw.get("metrics", {})
            payload["thresholds"] = {
                name: body.get("thresholds", {})
                for name, body in (raw.get("metrics") or {}).items()
                if isinstance(body, dict) and body.get("thresholds")
            }
        except json.JSONDecodeError as exc:
            print(f"record_k6_baseline_results: invalid JSON: {exc}", file=sys.stderr)
            return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"record_k6_baseline_results: wrote {OUT.relative_to(ROOT)} ({payload['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
