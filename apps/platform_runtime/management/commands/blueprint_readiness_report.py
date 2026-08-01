"""Report — and optionally settle — blueprint readiness for real tenants.

Readiness is per-tenant, so "are our blueprints at 100%?" can only be answered
against real schools. This command answers it, names every shortfall, and (with
``--record-manual-collection``) closes the one shortfall an operator can close
without a PSP: recording that a school reconciles fees by hand.

    python manage.py blueprint_readiness_report
    python manage.py blueprint_readiness_report --school gilead-tech-high
    python manage.py blueprint_readiness_report --school gilead-tech-high \\
        --record-manual-collection --note "Cash at the bursary"

Read-only unless ``--record-manual-collection`` is passed. That flag writes an
explicit, actor-less but audited posture — the same record the tenant UI writes
— and is refused for a school that already has a live rail (there is nothing to
settle) or an existing posture unless ``--force`` is given.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.finance.fee_collection_posture import (
    POSTURE_MANUAL,
    get_recorded_posture,
    record_collection_posture,
    resolve_live_collection_state,
)
from apps.platform_runtime.blueprint_contract import list_blueprints
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.readiness_meters import blueprint_readiness
from apps.schools.models import School


class Command(BaseCommand):
    help = "Report blueprint readiness per tenant and optionally record a manual collection posture."

    def add_arguments(self, parser):
        parser.add_argument("--school", default="", help="School slug (default: every active school).")
        parser.add_argument(
            "--record-manual-collection",
            action="store_true",
            help="Record a manual-reconciliation fee-collection posture (WRITES).",
        )
        parser.add_argument("--note", default="", help="Note stored with the posture.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite an existing recorded posture.",
        )

    def handle(self, *args, **options):
        slug = (options["school"] or "").strip()
        schools = (
            School.objects.filter(slug=slug)
            if slug
            else School.objects.filter(is_active=True).order_by("name")
        )
        schools = list(schools)
        if not schools:
            raise CommandError(f"No school matched {slug!r}." if slug else "No active schools.")

        for school in schools:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{school.name} ({school.slug})"))
            if options["record_manual_collection"]:
                self._record(school, note=options["note"], force=options["force"])
            self._report(school)

    def _record(self, school, *, note: str, force: bool) -> None:
        state = resolve_live_collection_state(school)
        if state["live"]:
            self.stdout.write(
                self.style.WARNING(
                    "  skipped: a live payment rail is already available — nothing to settle."
                )
            )
            return
        existing = get_recorded_posture(school)
        if existing and not force:
            self.stdout.write(
                self.style.WARNING(
                    f"  skipped: posture already recorded ({existing['mode']}); pass --force to overwrite."
                )
            )
            return
        record_collection_posture(school, mode=POSTURE_MANUAL, note=note)
        self.stdout.write(self.style.SUCCESS("  recorded: manual reconciliation posture"))

    def _report(self, school) -> None:
        below = 0
        for row in list_blueprints(tenant_safe_only=True):
            preview = preview_blueprint(row["key"], school=school, platform_operator=False)
            result = blueprint_readiness(preview, school=school)
            if result["complete"]:
                self.stdout.write(f"  100  {row['key']}")
                continue
            below += 1
            self.stdout.write(
                self.style.WARNING(
                    f"  {result['value']:>3}  {row['key']} — pending: {', '.join(result['unmet'])}"
                )
            )
        if below:
            self.stdout.write(self.style.WARNING(f"  {below} blueprint(s) below 100."))
        else:
            self.stdout.write(self.style.SUCCESS("  every tenant-safe blueprint is at 100."))
