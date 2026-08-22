"""Find and re-run imports whose worker died mid-apply.

The production shape this exists for: a bundle sits at ``APPLYING`` because the
worker that claimed it was killed (deploy, OOM, connection exhaustion) before it
could mark the bundle FAILED. The tenant sees "Writing records into your
school..." and, until the staleness fix, saw it indefinitely.

Recovering one used to mean hand-editing state in a production shell::

    b = MigrationBundle.objects.get(pk=...)
    b.mark_status(BundleStatus.MAPPED)      # no safety check whatsoever
    enqueue_apply(b.pk, dry_run=False)

That bypasses every guardrail :func:`repair.repair_readiness` exists to enforce —
most importantly the financial control-total lock and the finance-must-be-atomic
rule — so a mistyped id could re-apply money data in non-atomic mode. This command
routes the same recovery through ``repair_bundle``, which refuses exactly those
cases and re-applies idempotently (apply is upsert-by-external-id, so records that
already landed are updated in place, never duplicated).

READ-ONLY BY DEFAULT. Listing is the default action; ``--repair`` is required to
change anything, and it acts on ONE explicit bundle id — never a bulk sweep::

    python manage.py mc_recover_import                        # what is stuck?
    python manage.py mc_recover_import --school gilead        # ...for one school
    python manage.py mc_recover_import --bundle-id 42         # why / why not
    python manage.py mc_recover_import --bundle-id 42 --repair
    python manage.py mc_recover_import --bundle-id 42 --repair --sync
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.migration_cloud.models import BundleStatus, MigrationBundle
from apps.migration_cloud.repair import (
    live_apply_in_flight,
    prior_apply_evidence,
    repair_bundle,
    repair_readiness,
    supersede_wedged_apply,
    tenant_apply_stuck,
)

# Statuses worth listing: a wedged apply, plus the two states repair_readiness
# already treats as recoverable.
_CANDIDATE_STATUSES = (
    BundleStatus.APPLYING,
    BundleStatus.MAPPED,
    BundleStatus.FAILED,
    BundleStatus.APPLIED,
)


class Command(BaseCommand):
    help = "List imports that stalled mid-apply, and safely re-run one."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            dest="school",
            default="",
            help="Limit to one school by slug, subdomain, or pk.",
        )
        parser.add_argument(
            "--bundle-id",
            dest="bundle_id",
            type=int,
            default=None,
            help="Inspect one bundle. Required by --repair.",
        )
        parser.add_argument(
            "--repair",
            action="store_true",
            help="Re-run the bundle given by --bundle-id (durable/off-request).",
        )
        parser.add_argument(
            "--sync",
            action="store_true",
            help="With --repair, apply synchronously in this shell (no outbox queue).",
        )
        parser.add_argument(
            "--force-reclaim",
            action="store_true",
            help=(
                "With --repair on an APPLYING bundle: retire wedged outbox rows and "
                "reset to MAPPED when repair_readiness refuses with status:APPLYING."
            ),
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _queryset(self, school_ref: str):
        # tenant-isolation-allow: operator recovery command, deliberately cross-tenant
        # unless --school narrows it; run from a trusted shell, never from a request.
        qs = MigrationBundle.objects.filter(status__in=_CANDIDATE_STATUSES)
        if school_ref:
            from apps.schools.models import School

            school = (
                School.objects.filter(slug=school_ref).first()
                or School.objects.filter(subdomain=school_ref).first()
            )
            if school is None and school_ref.isdigit():
                school = School.objects.filter(pk=school_ref).first()
            if school is None:
                raise CommandError(f"No school matches {school_ref!r}.")
            qs = qs.filter(school=school)
        return qs.select_related("school").order_by("-created_at")

    def _force_reclaim(self, bundle) -> int:
        """Retire wedged apply rows; reset APPLYING→MAPPED when nothing is moving."""
        retired = supersede_wedged_apply(bundle)
        bundle.refresh_from_db()
        if bundle.status == BundleStatus.APPLYING and not live_apply_in_flight(bundle):
            bundle.mark_status(
                BundleStatus.MAPPED,
                summary_patch={"operator_force_reclaimed_at": timezone.now().isoformat()},
            )
        return retired

    def _describe(self, bundle) -> str:
        readiness = repair_readiness(bundle)
        if bundle.status == BundleStatus.APPLYING:
            state = "WEDGED" if tenant_apply_stuck(bundle) else "running"
        else:
            state = bundle.status
        school = getattr(bundle.school, "slug", None) or bundle.school_id or "-"
        verdict = "repairable" if readiness.repairable else f"no: {readiness.reason}"
        return f"  #{bundle.pk:<6} {school:<24} {state:<10} {verdict}"

    # ── entry point ──────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        bundle_id = options["bundle_id"]
        do_repair = options["repair"]
        do_sync = options["sync"]
        do_force = options["force_reclaim"]

        if do_repair and bundle_id is None:
            raise CommandError("--repair needs --bundle-id (it acts on one import).")
        if do_sync and not do_repair:
            raise CommandError("--sync requires --repair.")
        if do_force and not do_repair:
            raise CommandError("--force-reclaim requires --repair.")

        if bundle_id is not None:
            try:
                bundle = MigrationBundle.objects.select_related("school").get(pk=bundle_id)  # tenant-isolation-allow: explicit operator-supplied pk
            except MigrationBundle.DoesNotExist:
                raise CommandError(f"No bundle with id {bundle_id}.")

            readiness = repair_readiness(bundle)
            self.stdout.write(f"Bundle #{bundle.pk} — status {bundle.status}")
            self.stdout.write(f"  school:     {getattr(bundle.school, 'slug', '-')}")
            self.stdout.write(f"  stuck:      {tenant_apply_stuck(bundle)}")
            self.stdout.write(f"  in_flight:  {live_apply_in_flight(bundle)}")
            self.stdout.write(f"  repairable: {readiness.repairable}")
            self.stdout.write(f"  reason:     {readiness.reason}")
            if readiness.blockers:
                self.stdout.write(f"  blockers:   {', '.join(readiness.blockers)}")

            if not do_repair:
                self.stdout.write(
                    self.style.WARNING("\nRead-only. Add --repair to re-run this import.")
                )
                return

            if do_force or (
                bundle.status == BundleStatus.APPLYING
                and not readiness.repairable
                and "status:APPLYING" in (readiness.blockers or [])
            ) or (
                bundle.status == BundleStatus.MAPPED
                and tenant_apply_stuck(bundle)
                and prior_apply_evidence(bundle)
                and not readiness.repairable
            ):
                retired = self._force_reclaim(bundle)
                if retired:
                    self.stdout.write(f"  reclaimed:  superseded {retired} wedged outbox row(s)")
                bundle.refresh_from_db()
                readiness = repair_readiness(bundle)
                self.stdout.write(f"  after reclaim — repairable: {readiness.repairable}")

            result = repair_bundle(bundle_id=bundle.pk, off_http=not do_sync)
            if not result.ok:
                # A refusal is the guardrail doing its job — report it as such,
                # not as a crash, so an operator can act on the reason.
                self.stdout.write(self.style.ERROR(f"\nRefused: {result.message}"))
                if result.blockers:
                    self.stdout.write(f"blockers: {', '.join(result.blockers)}")
                return
            if result.ran:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\nApplied: {result.message} "
                        f"(created {result.created}, updated {result.updated}, "
                        f"held {result.quarantined})"
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"\nQueued: {result.message}"
                        + (f" (outbox {result.outbox_id})" if result.outbox_id else "")
                    )
                )
            self.stdout.write(
                f"status {result.before_status} -> {result.after_status}; "
                + (
                    "repair finished in this shell."
                    if result.ran
                    else "the worker will take it from here."
                )
            )
            return

        rows = list(self._queryset(options["school"])[:100])
        if not rows:
            self.stdout.write("No stalled or repairable imports.")
            return
        self.stdout.write(f"{len(rows)} candidate import(s):\n")
        self.stdout.write(f"  {'id':<7} {'school':<24} {'state':<10} verdict")
        for bundle in rows:
            self.stdout.write(self._describe(bundle))
        self.stdout.write(
            self.style.WARNING(
                "\nRead-only. Re-run one with: "
                "manage.py mc_recover_import --bundle-id <id> --repair"
            )
        )
