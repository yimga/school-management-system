#!/usr/bin/env python
"""How much tenant data does this database actually hold, per model?

WHY THIS EXISTS
---------------
A number measured against an empty database is a floor, not a capability, and
this platform keeps measuring itself against one. The admin autofill ratchet can
only freeze CODE-only metrics because CI's school has no rows: "0 of 460
prefilled" says nothing about whether prefill works. A browser sweep over an
empty tenant exercises empty states and calls it coverage. A report gate proves
a report is *registered*, not that it renders anything.

Somebody measured this once by hand and wrote down "0 of 141 tenant models have
25 or more rows". That is a fact with a shelf life, and re-deriving it costs an
afternoon each time. This makes it one command.

It is also the acceptance criterion for seed work: `ensure_demo_environment`
already composes `seed_demo` + `seed_demo_tenant_users`, so the open question is
not "is there a seeder" but "what does it leave empty". Run this before and
after.

WHAT COUNTS AS TENANT-SCOPED
----------------------------
A model with a direct ``school`` FK, or one that reaches ``schools.School``
through a FK chain (depth-limited). That is the same population the RLS gates
care about, deliberately: a table with rows nobody can see and a table with no
rows at all fail a demo the same way, and they should be countable together.

USAGE
-----
    python scripts/audit_tenant_data_coverage.py
    python scripts/audit_tenant_data_coverage.py --school demo-school --min 25
    python scripts/audit_tenant_data_coverage.py --json
    python scripts/audit_tenant_data_coverage.py --empty-only

Read-only. It runs COUNT queries and nothing else.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import logging  # noqa: E402

if __name__ == "__main__":
    # config.settings leaves DEBUG=True locally, so Django logs every query at
    # DEBUG -- and this issues one COUNT per tenant model, 504 of them. Without
    # this the report is buried under the SQL it produced itself. Done here
    # rather than in main() because django.setup() below logs as well, and
    # guarded by __main__ because a module-level logging.disable() is global:
    # one of those already cost this repo 115 inert assertLogs assertions.
    logging.disable(logging.INFO)

import django  # noqa: E402

django.setup()

from django.apps import apps as django_apps  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.models import ForeignKey, OneToOneField  # noqa: E402

MAX_RELATION_DEPTH = 3


def _school_model():
    return django_apps.get_model("schools", "School")


def _reaches_school(model, school_model, depth: int = 0, seen: set | None = None) -> str | None:
    """The FK path from ``model`` to School, or None. Breadth is bounded on purpose."""
    if depth > MAX_RELATION_DEPTH:
        return None
    seen = seen or set()
    if model in seen:
        return None
    seen = seen | {model}
    for field in model._meta.get_fields():
        if not isinstance(field, (ForeignKey, OneToOneField)):
            continue
        target = field.remote_field.model
        if target is school_model:
            return field.name
        nested = _reaches_school(target, school_model, depth + 1, seen)
        if nested:
            return f"{field.name}.{nested}"
    return None


def collect(min_rows: int, school_slug: str | None) -> dict:
    school_model = _school_model()
    school = None
    if school_slug:
        school = school_model.objects.filter(slug=school_slug).first()
        if school is None:
            raise SystemExit(f"no school with slug {school_slug!r}")

    rows: list[dict] = []
    for cfg in django_apps.get_app_configs():
        if not cfg.name.startswith("apps."):
            continue
        for model in cfg.get_models():
            if model is school_model:
                continue
            path = _reaches_school(model, school_model)
            if path is None:
                continue
            queryset = model._default_manager.all()
            scoped = False
            if school is not None and path == "school":
                queryset = queryset.filter(school=school)
                scoped = True
            try:
                count = queryset.count()
            except Exception as exc:  # a model whose table is absent is a finding, not a crash
                rows.append({
                    "model": f"{cfg.label}.{model.__name__}",
                    "table": model._meta.db_table,
                    "count": None,
                    "error": type(exc).__name__,
                    "via": path,
                    "scoped": scoped,
                })
                continue
            rows.append({
                "model": f"{cfg.label}.{model.__name__}",
                "table": model._meta.db_table,
                "count": count,
                "via": path,
                "scoped": scoped,
            })

    rows.sort(key=lambda r: (-(r["count"] or -1), r["model"]))
    counted = [r for r in rows if r["count"] is not None]
    return {
        "database": connection.settings_dict.get("NAME"),
        "vendor": connection.vendor,
        "school": school_slug,
        "min_rows": min_rows,
        "tenant_models": len(rows),
        "unreadable": len(rows) - len(counted),
        "empty": sum(1 for r in counted if r["count"] == 0),
        "below_min": sum(1 for r in counted if 0 < r["count"] < min_rows),
        "at_or_above_min": sum(1 for r in counted if r["count"] >= min_rows),
        "total_rows": sum(r["count"] for r in counted),
        "models": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min", type=int, default=25, help="rows a model needs to be 'populated' (default 25)")
    parser.add_argument("--school", help="scope directly-scoped models to this school slug")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--empty-only", action="store_true", help="list only the models with zero rows")
    parser.add_argument("--top", type=int, default=15, help="how many populated models to list")
    parser.add_argument(
        "--fail-under",
        type=int,
        help="exit 1 unless at least this many models hold --min rows. For use as a gate "
        "once a reference dataset exists; omit for a plain report.",
    )
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    report = collect(args.min, args.school)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 0

    print(f"database : {report['database']} ({report['vendor']})")
    if report["school"]:
        print(f"school   : {report['school']}")
    print(f"tenant-scoped models : {report['tenant_models']}")
    print(f"  holding >= {report['min_rows']:<4d}      : {report['at_or_above_min']}")
    print(f"  holding 1..{report['min_rows'] - 1:<4d}     : {report['below_min']}")
    print(f"  empty              : {report['empty']}")
    if report["unreadable"]:
        print(f"  UNREADABLE         : {report['unreadable']}  (table missing or query failed)")
    print(f"  total rows         : {report['total_rows']}")

    if args.empty_only:
        print("\nempty models:")
        for row in sorted(r["model"] for r in report["models"] if r["count"] == 0):
            print(f"  {row}")
    else:
        populated = [r for r in report["models"] if (r["count"] or 0) > 0][: args.top]
        if populated:
            print(f"\nmost populated ({len(populated)} of {report['tenant_models'] - report['empty']} non-empty):")
            for row in populated:
                print(f"  {row['count']:8d}  {row['model']}")
        else:
            print("\nEvery tenant-scoped model is empty. Any data-dependent measurement")
            print("taken against this database is a floor, not a capability.")

    unreadable = [r for r in report["models"] if r["count"] is None]
    if unreadable:
        print(f"\nunreadable ({len(unreadable)}):")
        for row in unreadable[:10]:
            print(f"  {row['model']}  -> {row['error']}")

    if args.fail_under is not None and report["at_or_above_min"] < args.fail_under:
        print(
            f"\nFAIL: {report['at_or_above_min']} model(s) hold {report['min_rows']}+ rows, "
            f"required {args.fail_under}."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
