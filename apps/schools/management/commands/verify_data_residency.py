"""Wave E — G4: report data-residency alignment per tenant.

Usage::

    python manage.py verify_data_residency
    python manage.py verify_data_residency --school <slug>
    python manage.py verify_data_residency --fix-derive   # backfill blank data_region from country_code

Reports one row per school: slug · country · regulatory region ·
operational alias · aligned? Exit code is non-zero only when ``--strict``
is passed and any mismatch is found, so the command is safe to wire into
nightly cron without alerting on transitional state.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Report data-residency alignment (regulatory data_region vs operational regional_cluster)."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="Optional school slug filter.")
        parser.add_argument("--strict", action="store_true",
                            help="Exit code 1 when any school is misaligned.")
        parser.add_argument("--fix-derive", action="store_true",
                            help="Backfill blank data_region from country_code.")

    def handle(self, *args, **opts):
        from apps.schools.models import School
        from apps.schools.data_residency import (
            derive_default_region,
            effective_region,
            is_aligned,
            is_canonical,
        )

        slug_filter = (opts.get("school") or "").strip()
        strict = bool(opts.get("strict"))
        fix_derive = bool(opts.get("fix_derive"))

        # tenant-isolation-allow: residency verifier scans every tenant by design
        qs = School.objects.filter(is_active=True).only(
            "id", "slug", "country_code", "data_region", "regional_cluster",
        )
        if slug_filter:
            qs = qs.filter(slug=slug_filter)

        misaligned = 0
        backfilled = 0
        total = 0
        for school in qs.iterator():
            total += 1
            derived = derive_default_region(school.country_code or "")
            current_explicit = (school.data_region or "").strip()
            operational = (school.regional_cluster or "").strip() or "—"

            if fix_derive and not current_explicit and derived != "global":
                School.objects.filter(pk=school.pk).update(data_region=derived)
                school.data_region = derived
                backfilled += 1

            effective = effective_region(school)
            aligned = is_aligned(school)
            canonical = is_canonical(effective)
            warn = "" if aligned else " ⚠ misaligned"
            if not canonical:
                warn += " ⚠ non-canonical-region"
            if not aligned:
                misaligned += 1
            line = (
                f"{school.slug:30s}  country={school.country_code or '--':2s}  "
                f"regulatory={effective:18s}  operational={operational:18s}{warn}"
            )
            self.stdout.write(line)

        self.stdout.write("")
        summary = f"verified {total} school(s); misaligned {misaligned}"
        if fix_derive:
            summary += f"; backfilled data_region for {backfilled}"
        if misaligned == 0:
            self.stdout.write(self.style.SUCCESS(summary))
        else:
            self.stdout.write(self.style.WARNING(summary))

        if strict and misaligned > 0:
            raise SystemExit(1)
