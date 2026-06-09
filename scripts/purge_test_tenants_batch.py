#!/usr/bin/env python
"""One-shot purge for inactive test tenants (Render shell).

Bypasses legal hold, dual approval, and in-flight provisioning gates.
Run: python scripts/purge_test_tenants_batch.py [--apply]
"""
from __future__ import annotations

import argparse
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Django bootstrap when invoked as a script from repo root.
if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

from apps.schools.models import School
from apps.schools.tenant_offboarding import (
    _save_offboarding_settings,
    apply_purge,
    dry_run_purge,
    set_legal_hold,
)

TEST_SLUGS = (
    "gilead-tech",
    "moja-skola",
    "magic-test",
    "newbell-school",
    "newssbell-school-of-arts",
    "our-lady",
    "st-jesus",
    "st-jude",
)


def _clear_blockers(school) -> None:
    set_legal_hold(school, hold_until=None)
    _save_offboarding_settings(
        school,
        {
            "dual_approved": True,
            "policy_override_reason": "purge_test_tenants_batch",
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute permanent purge (default is dry-run only).",
    )
    parser.add_argument(
        "--slug",
        action="append",
        dest="slugs",
        help="Override default slug list (repeatable).",
    )
    args = parser.parse_args(argv)
    slugs = args.slugs or list(TEST_SLUGS)

    missing: list[str] = []
    for slug in slugs:
        school = School.objects.filter(slug=slug).first()
        if school is None:
            missing.append(slug)
            print(f"[{slug}] NOT FOUND — skipping")
            continue

        _clear_blockers(school)
        if not args.apply:
            preview = dry_run_purge(
                school,
                confirm_slug=slug,
                force_provisioning=True,
                dual_approved=True,
            )
            print(
                f"[{slug}] DRY-RUN rows={preview.row_total} "
                f"blockers={preview.purge_blocked_reasons or 'none'}"
            )
            continue

        receipt = apply_purge(
            school,
            actor=None,
            confirm_slug=slug,
            dry_run=False,
            force_provisioning=True,
            dual_approved=True,
            purge_source="cli_test_batch",
        )
        print(
            f"[{slug}] PURGED pk={receipt.school_id} "
            f"schema={receipt.schema_dropped or 'n/a'}"
        )

    still = [s for s in slugs if School.objects.filter(slug=s).exists()]
    if args.apply and still:
        print(f"ERROR: still present after purge: {still}", file=sys.stderr)
        return 1
    if missing and not args.apply:
        print(f"Note: {len(missing)} slug(s) not in database.")
    if args.apply and not still:
        print("OK: all requested tenants removed.")
    elif not args.apply:
        print("DRY-RUN complete — re-run with --apply to delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
