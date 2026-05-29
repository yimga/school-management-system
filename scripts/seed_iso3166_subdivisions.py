#!/usr/bin/env python3
"""Phase 3B — seed ISO 3166-2 subdivisions into SubdivisionRegistry (CI wrapper)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed ISO 3166-2 subdivisions (Phase 3B)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--country",
        action="append",
        default=None,
        dest="countries",
        metavar="ALPHA2",
    )
    parser.add_argument("--skip-matrix", action="store_true")
    args = parser.parse_args()

    import django

    django.setup()

    from django.db import transaction

    from apps.registries.services import (
        seed_iso3166_subdivisions,
        update_governance_matrix_subdivision_flags,
    )

    if args.dry_run:
        result = seed_iso3166_subdivisions(dry_run=True, country_codes=args.countries)
        print(
            "seed_iso3166_subdivisions: DRY RUN "
            f"countries={result.countries_processed} "
            f"with_subdivisions={len(result.countries_with_subdivisions)}"
        )
        return 0

    with transaction.atomic():
        result = seed_iso3166_subdivisions(country_codes=args.countries)
        matrix_flagged = 0
        if not args.skip_matrix:
            matrix_flagged = update_governance_matrix_subdivision_flags()

    if not args.quiet:
        print(
            "seed_iso3166_subdivisions: OK "
            f"created={result.subdivisions_created} "
            f"updated={result.subdivisions_updated} "
            f"countries={len(result.countries_with_subdivisions)} "
            f"matrix_flags={matrix_flagged}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
