"""P1-Forensic — operator inspect command for tenant Migration Cloud state."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Inspect Migration Cloud bundles/artifacts/companion receipts for a tenant "
        "slug (e.g. new-school). Prints classification for upload-OK / school-empty triage."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--slug",
            required=True,
            help="School slug or subdomain (e.g. new-school)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Max bundles to list (default 20)",
        )

    def handle(self, *args, **options):
        slug = (options["slug"] or "").strip()
        limit = max(1, min(int(options["limit"]), 100))
        if not slug:
            raise CommandError("--slug is required")

        from apps.schools.models import School
        from apps.customers.models import Client
        from apps.schools.tenant_offboarding import get_schema_name
        from apps.migration_cloud.models import (
            MigrationBundle,
            CompanionUploadReceipt,
        )
        from apps.migration_cloud.schema_binding import resolve_school_schema_name

        school = (
            School.objects.filter(slug=slug).first()
            or School.objects.filter(subdomain=slug).first()
        )
        if school is None:
            raise CommandError(f"No School with slug/subdomain={slug!r}")

        client = Client.objects.filter(school=school).first()
        client_schema = getattr(client, "schema_name", None) if client else None
        helper_schema = get_schema_name(school)
        resolved = resolve_school_schema_name(school)

        entitled = None
        try:
            from apps.billing.entitlements import can

            entitled = can(school, "migration_cloud")
        except Exception as exc:  # noqa: BLE001
            entitled = f"error:{type(exc).__name__}"

        self.stdout.write(
            self.style.NOTICE(
                f"school_id={school.pk} slug={school.slug} subdomain={school.subdomain}"
            )
        )
        self.stdout.write(
            f"schema client={client_schema!r} helper={helper_schema!r} "
            f"resolved={resolved!r} migration_cloud_entitled={entitled}"
        )

        receipts = CompanionUploadReceipt.objects.filter(tenant=school).count()
        self.stdout.write(f"companion_receipts={receipts}")

        qs = MigrationBundle.objects.filter(school=school).order_by("-created_at")[:limit]
        total = MigrationBundle.objects.filter(school=school).count()
        self.stdout.write(f"bundles total={total} showing={qs.count()}")

        for b in qs:
            arts = b.artifacts.count()
            err = (b.size_summary or {}).get("error")
            apply_tot = (b.mapping_summary or {}).get("apply_totals")
            classif = _classify(b, arts=arts, resolved_schema=resolved)
            self.stdout.write(
                f"  bundle={b.pk} status={b.status} schema={b.schema_name!r} "
                f"method={b.intake_method} arts={arts} class={classif} "
                f"err={err!r} apply={apply_tot!r}"
            )


def _classify(bundle, *, arts: int, resolved_schema: str) -> str:
    status = bundle.status
    schema = (bundle.schema_name or "").strip()
    if status == "PENDING" and arts == 0:
        return "pending_or_companion_awaiting_decrypt"
    if status == "INGESTING" and arts == 0:
        return "P0B_ingest_theater_zero_artifacts"
    if arts > 0 and status in ("PENDING", "INGESTING", "PROFILED", "CLASSIFIED"):
        return "advance_stuck_or_in_progress"
    if status == "MAPPED":
        return "mapped_awaiting_confirm_apply"
    if status in ("APPLIED", "RECONCILED") and not schema:
        return "P0A_applied_empty_schema"
    if status in ("APPLIED", "RECONCILED") and resolved_schema and schema != resolved_schema:
        return "schema_mismatch_vs_client"
    if status in ("APPLIED", "RECONCILED"):
        return "applied_check_quarantine_and_ui"
    if status in ("FAILED", "ABORTED"):
        return "failed_or_aborted"
    return "other"
