"""Audit / repair rows that cannot sync because nothing owns them.

Read-only by default. ``--apply`` writes, and even then only rows whose owner was
INFERRED from referring data; foreign and ambiguous rows are never touched. See
:mod:`apps.sync_engine.ownership_repair`.

    python manage.py repair_sync_ownership --school gilead-tech
    python manage.py repair_sync_ownership --school gilead-tech --apply
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.sync_engine.ownership_repair import (
    AMBIGUOUS,
    ASSIGNABLE,
    FOREIGN,
    ORPHAN,
    apply_ownership_repair,
    plan_ownership_repair,
)


class Command(BaseCommand):
    help = "Find rows with no school (never syncable) and claim the provable ones."

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="School slug, subdomain, or pk.")
        parser.add_argument("--apply", action="store_true", help="Write the assignable rows.")
        parser.add_argument(
            "--include-orphans",
            action="store_true",
            help="Also claim rows nothing references (no evidence — operator decision).",
        )
        parser.add_argument("--limit", type=int, default=40, help="Rows to list per verdict.")

    def _school(self, ref):
        from apps.schools.models import School

        s = (
            School.objects.filter(slug=ref).first()
            or School.objects.filter(subdomain=ref).first()
        )
        if s is None:
            try:
                s = School.objects.filter(pk=ref).first()
            except Exception:  # noqa: BLE001 — a non-uuid ref is simply "not found"
                s = None
        if s is None:
            raise CommandError(f"No school matches {ref!r}.")
        return s

    def handle(self, *args, **options):
        school = self._school(options["school"])
        plan = plan_ownership_repair(school)
        counts = plan["counts"]

        self.stdout.write(f"School: {school.slug} ({school.pk})")
        self.stdout.write(
            "Unowned rows found: "
            + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none")
        )

        limit = options["limit"]
        for verdict, blurb in (
            (ASSIGNABLE, "will be claimed (referring rows all point at this school)"),
            (ORPHAN, "nothing references these — claimed only with --include-orphans"),
            (AMBIGUOUS, "referenced by THIS school and others — left alone"),
            (FOREIGN, "referenced only by OTHER schools — left alone"),
        ):
            rows = [c for c in plan["candidates"] if c.verdict == verdict]
            if not rows:
                continue
            self.stdout.write(f"\n{verdict.upper()} ({len(rows)}) — {blurb}")
            for c in rows[:limit]:
                ev = "; ".join(f"{k}->{v}" for k, v in c.evidence.items()) or "no referrers"
                self.stdout.write(f"   {c.entity_type:<20} pk={c.pk!s:<8} {ev}")
            if len(rows) > limit:
                self.stdout.write(f"   ... {len(rows) - limit} more not shown")

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING("\nDry run. Re-run with --apply to write the changes.")
            )
            return

        result = apply_ownership_repair(
            school, plan=plan, include_orphans=options["include_orphans"]
        )
        if not result["total"]:
            self.stdout.write("Nothing to claim.")
            return
        self.stdout.write(
            self.style.SUCCESS(f"\nClaimed {result['total']} row(s) for {school.slug}:")
        )
        for entity_type, n in sorted(result["updated"].items()):
            self.stdout.write(f"   {entity_type}: {n}")
        self.stdout.write("These rows are now eligible for the next delta bundle.")
