"""Retag misclassified import files and re-apply one bundle safely.

Typical use after a classifier fix (e.g. telephone directory routed to
``custom_fields`` instead of ``staff``)::

    python manage.py mc_retag_and_repair --bundle-id 86 --dry-run
    python manage.py mc_retag_and_repair --bundle-id 86 --apply
    python manage.py mc_retag_and_repair --bundle-id 86 --apply --force-reapply --sync

READ-ONLY by default. ``--apply`` runs catalog recommendations, refreshes
inference with current rules, then routes re-apply through
:func:`repair.repair_bundle` when the bundle is repairable, or through an
explicit ``--force-reapply`` path when it applied cleanly but was mis-tagged.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.migration_cloud.accelerators.runmycampus_canonical import is_valid_canonical_domain
from apps.migration_cloud.models import MigrationBundle
from apps.migration_cloud.repair import repair_bundle, repair_readiness


class Command(BaseCommand):
    help = "Apply catalog record-type fixes and repair one import bundle."

    def add_arguments(self, parser):
        parser.add_argument(
            "--bundle-id",
            type=int,
            required=True,
            help="Migration bundle pk (e.g. 86).",
        )
        parser.add_argument(
            "--school",
            default="",
            help="Optional school slug/subdomain/pk — refuses if bundle belongs elsewhere.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report planned retags and repair readiness (default when --apply omitted).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Retag from catalog shape, refresh inference, and repair.",
        )
        parser.add_argument(
            "--force-reapply",
            action="store_true",
            help=(
                "With --apply: re-import even when repair_readiness says the bundle "
                "applied cleanly (typical after retagging a misclassified file)."
            ),
        )
        parser.add_argument(
            "--sync",
            action="store_true",
            help="With --apply, run apply synchronously in this shell (no outbox queue).",
        )
        parser.add_argument(
            "--force-domain",
            default="",
            help="Force this canonical domain on matched artifacts (requires --filename-contains).",
        )
        parser.add_argument(
            "--filename-contains",
            default="",
            help="Case-insensitive substring match on artifact filename (with --force-domain).",
        )
        parser.add_argument(
            "--artifact-id",
            type=int,
            default=None,
            help="With --force-domain, retag one artifact by pk instead of filename match.",
        )

    def handle(self, *args, **options):
        if options["apply"] and options["dry_run"]:
            raise CommandError("Pass --dry-run or --apply, not both.")
        if options["sync"] and not options["apply"]:
            raise CommandError("--sync requires --apply.")
        if options["force_reapply"] and not options["apply"]:
            raise CommandError("--force-reapply requires --apply.")

        dry_run = not options["apply"]
        bundle = self._load_bundle(options["bundle_id"], options["school"])
        self._print_bundle_header(bundle)

        forced = self._maybe_force_domain(
            bundle,
            domain=(options["force_domain"] or "").strip(),
            filename_contains=(options["filename_contains"] or "").strip(),
            artifact_id=options["artifact_id"],
            dry_run=dry_run,
        )

        planned = self._planned_catalog_retags(bundle)
        self._print_planned_retags(planned)

        readiness = repair_readiness(bundle)
        self.stdout.write(f"repairable: {readiness.repairable}")
        self.stdout.write(f"reason:     {readiness.reason}")
        if readiness.blockers:
            self.stdout.write(f"blockers:   {', '.join(readiness.blockers)}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nRead-only. Re-run with --apply to retag, refresh inference, and repair."
                )
            )
            return

        self._apply_retags(bundle, planned_count=len(planned))
        self._refresh_inference(bundle.pk)

        readiness = repair_readiness(bundle)
        if readiness.repairable:
            result = repair_bundle(bundle_id=bundle.pk, off_http=not options["sync"])
            self._print_apply_result(result)
            return

        if options["force_reapply"]:
            result = self._force_reapply(bundle, sync=options["sync"])
            self._print_apply_result(result)
            return

        self.stdout.write(
            self.style.ERROR(f"\nRepair refused after retag: {readiness.reason}")
        )
        if readiness.blockers:
            self.stdout.write(f"blockers: {', '.join(readiness.blockers)}")
        self.stdout.write(
            self.style.WARNING(
                "Add --force-reapply to re-import after retagging a cleanly-applied bundle."
            )
        )

    def _load_bundle(self, bundle_id: int, school_ref: str) -> MigrationBundle:
        try:
            bundle = MigrationBundle.objects.select_related("school").get(pk=bundle_id)  # tenant-isolation-allow: operator-supplied bundle pk
        except MigrationBundle.DoesNotExist:
            raise CommandError(f"No bundle with id {bundle_id}.")
        if school_ref:
            from apps.migration_cloud.management.school_resolution import resolve_school_or_error

            school = resolve_school_or_error(school_ref)
            if bundle.school_id != school.pk:
                raise CommandError(
                    f"Bundle #{bundle_id} belongs to {getattr(bundle.school, 'slug', bundle.school_id)!r}, "
                    f"not {school_ref!r}."
                )
        return bundle

    def _print_bundle_header(self, bundle: MigrationBundle) -> None:
        self.stdout.write(f"Bundle #{bundle.pk} — status {bundle.status}")
        self.stdout.write(f"  school: {getattr(bundle.school, 'slug', '-')}")
        for art in bundle.artifacts.filter(quarantined=False).order_by("pk"):
            tag = (art.assigned_domain or "").strip() or "(auto)"
            self.stdout.write(
                f"  artifact #{art.pk}: {art.filename or art.path_within_bundle} -> {tag}"
            )

    def _planned_catalog_retags(self, bundle: MigrationBundle) -> list[dict[str, object]]:
        from apps.migration_cloud.catalog_preflight import assess_bundle_catalog_routing

        report = assess_bundle_catalog_routing(bundle)
        planned: list[dict[str, object]] = []
        for finding in report.get("artifacts") or []:
            if not isinstance(finding, dict):
                continue
            assigned = str(finding.get("assigned_domain") or "").strip() or "(auto)"
            recommended = str(finding.get("recommended_domain") or "").strip()
            severity = str(finding.get("severity") or "ok")
            if not recommended or recommended == assigned or severity == "ok":
                continue
            planned.append(finding)
        return planned

    def _print_planned_retags(self, planned: list[dict[str, object]]) -> None:
        if not planned:
            self.stdout.write("\nCatalog retags: none suggested.")
            return
        self.stdout.write(f"\nCatalog retags ({len(planned)} file(s)):")
        for row in planned:
            self.stdout.write(
                f"  #{row.get('artifact_id')} {row.get('filename')}: "
                f"{row.get('assigned_domain') or '(auto)'} -> {row.get('recommended_domain')} "
                f"({row.get('severity')})"
            )

    def _maybe_force_domain(
        self,
        bundle: MigrationBundle,
        *,
        domain: str,
        filename_contains: str,
        artifact_id: int | None,
        dry_run: bool,
    ) -> int:
        if not domain:
            return 0
        if not is_valid_canonical_domain(domain):
            raise CommandError(f"Invalid canonical domain {domain!r}.")
        if artifact_id is None and not filename_contains:
            raise CommandError("--force-domain requires --artifact-id or --filename-contains.")

        qs = bundle.artifacts.filter(quarantined=False)
        if artifact_id is not None:
            qs = qs.filter(pk=artifact_id)
        elif filename_contains:
            needle = filename_contains.casefold()
            matches = [
                art
                for art in qs
                if needle in (art.filename or art.path_within_bundle or "").casefold()
            ]
            if not matches:
                raise CommandError(
                    f"No artifact filename contains {filename_contains!r} on bundle #{bundle.pk}."
                )
            changed = 0
            for art in matches:
                if art.assigned_domain == domain:
                    continue
                self.stdout.write(
                    f"force-domain: #{art.pk} {art.filename} -> {domain}"
                    + (" (dry-run)" if dry_run else "")
                )
                if not dry_run:
                    art.assigned_domain = domain
                    art.save(update_fields=["assigned_domain", "updated_at"])
                changed += 1
            return changed

        art = qs.first()
        if art is None:
            raise CommandError(f"Artifact #{artifact_id} not found on bundle #{bundle.pk}.")
        if art.assigned_domain == domain:
            return 0
        self.stdout.write(
            f"force-domain: #{art.pk} {art.filename} -> {domain}"
            + (" (dry-run)" if dry_run else "")
        )
        if not dry_run:
            art.assigned_domain = domain
            art.save(update_fields=["assigned_domain", "updated_at"])
        return 1

    def _apply_retags(self, bundle: MigrationBundle, *, planned_count: int) -> None:
        from apps.migration_cloud.catalog_preflight import apply_catalog_recommendations
        from apps.migration_cloud.domain_overrides import sync_operator_assigned_domains

        changed = apply_catalog_recommendations(bundle)
        sync_operator_assigned_domains(bundle, rewind_status=False)
        self.stdout.write(
            f"Applied catalog retags to {changed} file(s)"
            + (f" ({planned_count} suggested)" if planned_count else "")
        )

    def _refresh_inference(self, bundle_id: int) -> None:
        from apps.migration_cloud.pipeline import refresh_bundle_inference

        summary = refresh_bundle_inference(bundle_id=bundle_id, use_accelerator=True)
        per = summary.get("per_artifact") or {}
        self.stdout.write("Inference refreshed:")
        for path, entry in sorted(per.items()):
            if isinstance(entry, dict):
                self.stdout.write(f"  {path}: {entry.get('domain')} ({entry.get('method')})")

    def _force_reapply(self, bundle: MigrationBundle, *, sync: bool):
        from django.utils import timezone

        from apps.migration_cloud.models import BundleStatus
        from apps.migration_cloud.progress import APPLY_RUN_EPOCH_KEY
        from apps.migration_cloud.repair import RepairResult, _financial_guardrail_locked, _has_finance

        if _financial_guardrail_locked(bundle):
            return RepairResult(
                ok=False,
                ran=False,
                message=(
                    "Financial control-total lock is active — reconcile totals before re-import."
                ),
                before_status=bundle.status,
                after_status=bundle.status,
                blockers=["financial_guardrail_failed"],
            )
        has_finance = _has_finance(bundle)
        if has_finance and not bool(getattr(bundle, "apply_atomic", False)):
            return RepairResult(
                ok=False,
                ran=False,
                message="Finance artifacts require atomic apply before force re-import.",
                before_status=bundle.status,
                after_status=bundle.status,
                blockers=["finance_requires_atomic"],
            )

        from apps.migration_cloud.apply_progress_guard import reset_apply_progress

        before = bundle.status
        now_iso = timezone.now().isoformat()
        bundle.mark_status(
            BundleStatus.MAPPED,
            summary_patch={
                "operator_retag_reapply_at": now_iso,
                APPLY_RUN_EPOCH_KEY: now_iso,
                "unified_progress_hwm": {"epoch": now_iso, "pct": 0.0},
            },
        )
        reset_apply_progress(bundle)

        if sync:
            from apps.migration_cloud.models import FinancialMismatchError
            from apps.migration_cloud.orchestrator import apply_bundle

            try:
                result = apply_bundle(bundle_id=bundle.pk, dry_run=False)
            except FinancialMismatchError:
                bundle.refresh_from_db()
                return RepairResult(
                    ok=False,
                    ran=True,
                    message=(
                        "Re-import stopped on the financial control-total check — "
                        "reconcile totals before retrying."
                    ),
                    before_status=before,
                    after_status=bundle.status,
                    blockers=["financial_guardrail_failed"],
                )
            bundle.refresh_from_db()
            return RepairResult(
                ok=bundle.status in (BundleStatus.APPLIED, BundleStatus.RECONCILED),
                ran=True,
                message=(
                    f"Re-imported after retag: {result.total_created} created, "
                    f"{result.total_updated} updated, {result.total_quarantined} held."
                ),
                before_status=before,
                after_status=bundle.status,
                created=result.total_created,
                updated=result.total_updated,
                quarantined=result.total_quarantined,
            )

        from apps.migration_cloud.celery_tasks import enqueue_apply
        from apps.migration_cloud.repair import supersede_wedged_apply

        supersede_wedged_apply(bundle)
        queued = enqueue_apply(
            bundle.pk,
            dry_run=False,
            reconcile_after=True,
            force=True,
        )
        oid = str(getattr(queued, "outbox_id", None) or getattr(queued, "id", "") or "")
        return RepairResult(
            ok=True,
            ran=False,
            queued=True,
            outbox_id=oid,
            message="Re-import queued after retag. Refresh the review page for results.",
            before_status=before,
            after_status=BundleStatus.MAPPED,
        )

    def _print_apply_result(self, result) -> None:
        if not result.ok:
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
        self.stdout.write(f"status {result.before_status} -> {result.after_status}")
