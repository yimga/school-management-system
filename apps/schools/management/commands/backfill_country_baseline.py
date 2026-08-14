"""Backfill the country baseline onto EXISTING tenants (platform-wide).

``provision_country_baseline`` seeds a school's country minimum defaults — terms
(with real dates), grading scale, subjects + national codes, TVET trades, the
country admission-number template, the specialty↔subject curriculum, and the
teaching + per-trade grids. New tenants get all of it at provisioning; already-
provisioned tenants (created before this feature shipped, or via a husk/seed path)
never re-enter Phase B, so they miss it. This command closes that gap for the
installed base.

Everything ``provision_country_baseline`` does is idempotent and guarded — an
uploaded subject catalog, a school that already issued admission numbers, a
general-ed school (no trades), and an admin's own edits are all left untouched —
so this is safe to run repeatedly across every tenant.

Usage::

    manage.py backfill_country_baseline                  # all active schools
    manage.py backfill_country_baseline --dry-run        # report only, change nothing
    manage.py backfill_country_baseline --school <id|subdomain|slug>
    manage.py backfill_country_baseline --limit 200 --include-inactive
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q


class Command(BaseCommand):
    help = "Run provision_country_baseline on existing tenants (idempotent backfill)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school", dest="school", default=None,
            help="Backfill a single school by id, subdomain, or slug.",
        )
        parser.add_argument("--limit", type=int, default=None, help="Process at most N schools.")
        parser.add_argument(
            "--dry-run", action="store_true", help="List what would be backfilled; change nothing.",
        )
        parser.add_argument(
            "--include-inactive", action="store_true",
            help="Also process schools with is_active=False (husks/pending).",
        )

    def handle(self, *args, **opts):
        from apps.academics.structure_provisioning import provision_country_baseline
        from apps.schools.models import School

        qs = School.objects.all()
        if not opts["include_inactive"]:
            qs = qs.filter(is_active=True)
        if opts["school"]:
            key = str(opts["school"]).strip()
            conditions = Q(subdomain=key) | Q(slug=key)
            # School.id is a UUID — only add an id lookup when the key parses as
            # one, or a subdomain/slug string raises a UUID ValidationError.
            import uuid

            try:
                uuid.UUID(key)
                conditions |= Q(id=key)
            except (ValueError, TypeError, AttributeError):
                pass
            qs = qs.filter(conditions)
        qs = qs.order_by("id")
        if opts["limit"]:
            qs = qs[: opts["limit"]]

        processed = ok = failed = 0
        for school in qs:
            processed += 1
            if opts["dry_run"]:
                self.stdout.write(f"[dry-run] would backfill {school.id}  {school.name}")
                continue
            try:
                summary = provision_country_baseline(school)
                ok += 1
                highlights = {
                    k: summary.get(k)
                    for k in (
                        "terms", "subjects", "subject_codes", "trades",
                        "admission_template", "curriculum", "specialty_grid",
                    )
                }
                self.stdout.write(f"OK   {school.id}  {school.name}: {highlights}")
            except Exception as exc:  # noqa: BLE001 — one school never aborts the sweep
                failed += 1
                self.stderr.write(f"FAIL {school.id}  {school.name}: {type(exc).__name__}: {exc}")

        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING(f"Dry run: {processed} school(s) would be backfilled."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Backfill complete: {processed} processed, {ok} ok, {failed} failed.")
            )
