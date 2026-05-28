#!/usr/bin/env python3
"""CEZGP batch 1520 — Top FrictionEvent views by aggregate count."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "docs" / "generated" / "friction_top_views_report.json"


def _setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def aggregate(*, days: int, school_id: int | None, limit: int) -> list[dict]:
    from django.utils import timezone as dj_tz

    from apps.observability.models_friction import FrictionEvent

    since = dj_tz.now() - timedelta(days=days)
    qs = FrictionEvent.objects.filter(last_seen__gte=since)
    if school_id is not None:
        qs = qs.filter(school_id=school_id)

    buckets: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"view_name": "", "kind": "", "total_count": 0, "schools": set()}
    )
    for row in qs.values("view_name", "kind", "count", "school_id"):
        key = (row["view_name"] or "", row["kind"] or "")
        bucket = buckets[key]
        bucket["view_name"] = key[0]
        bucket["kind"] = key[1]
        bucket["total_count"] += int(row["count"] or 0)
        if row["school_id"]:
            bucket["schools"].add(row["school_id"])

    ranked = sorted(buckets.values(), key=lambda b: b["total_count"], reverse=True)[:limit]
    out: list[dict] = []
    for item in ranked:
        out.append(
            {
                "view_name": item["view_name"],
                "kind": item["kind"],
                "total_count": item["total_count"],
                "school_count": len(item["schools"]),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days.")
    parser.add_argument("--school-id", type=int, default=None, help="Optional school PK filter.")
    parser.add_argument("--limit", type=int, default=25, help="Max rows to return.")
    parser.add_argument("--write", action="store_true", help="Write JSON report.")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout.")
    args = parser.parse_args()

    try:
        _setup_django()
        rows = aggregate(days=args.days, school_id=args.school_id, limit=args.limit)
    except Exception as exc:  # noqa: BLE001 — CLI report must not crash on empty DB
        print(f"report_friction_top_views: WARN ({exc})", file=sys.stderr)
        rows = []

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days": args.days,
        "school_id": args.school_id,
        "row_count": len(rows),
        "rows": rows,
    }

    if args.write:
        DEFAULT_OUT.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {DEFAULT_OUT}")

    if args.json or not args.write:
        print(json.dumps(payload, indent=2))

    for row in rows[:10]:
        print(
            f"  {row['view_name'] or '(anonymous)'} [{row['kind']}]: {row['total_count']}",
            file=sys.stderr,
        )

    print(f"report_friction_top_views: OK ({len(rows)} views)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
