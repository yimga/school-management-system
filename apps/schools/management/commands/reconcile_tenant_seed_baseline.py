"""Reconcile inferred platform defaults for existing tenant rows."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q


class Command(BaseCommand):
    help = (
        "Idempotently fill missing tenant localization, education classification, "
        "approved education profile, and default plan values without overwriting choices."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            default="",
            help="Limit to one active school by UUID, slug, or subdomain.",
        )
        parser.add_argument(
            "--write",
            action="store_true",
            help=(
                "Persist the reconciliation. Without it the command reports exactly "
                "what it WOULD change and rolls back, because this touches every "
                "active school's stored localization, classification and plan."
            ),
        )

    def handle(self, *args, **options):
        from apps.schools.models import School
        from apps.schools.seed_reconciliation import reconcile_tenant_seed_baseline

        qs = School.objects.filter(is_active=True).order_by("slug")
        key = str(options.get("school") or "").strip()
        if key:
            query = Q(slug=key) | Q(subdomain=key)
            try:
                import uuid

                uuid.UUID(key)
                query |= Q(pk=key)
            except (ValueError, TypeError, AttributeError):
                pass
            qs = qs.filter(query)
        schools = list(qs)
        if key and not schools:
            raise CommandError(f"Active school not found: {key}")
        if not schools:
            self.stdout.write(self.style.WARNING("No active schools to reconcile."))
            return

        write = bool(options.get("write"))
        changed = 0
        # The service persists as it resolves, so a truthful preview means letting
        # it run inside a transaction and rolling back -- that reports what WOULD
        # change rather than a second, drifting estimate of it.
        with transaction.atomic():
            for school in schools:
                result = reconcile_tenant_seed_baseline(school)
                if result.changed:
                    changed += 1
                state = ", ".join(result.changed_fields) if result.changed else "already complete"
                self.stdout.write(
                    f"{result.school_slug}: {state}; "
                    f"systems={list(result.education_system_types)}; "
                    f"levels={list(result.education_levels)}; "
                    f"profile={result.education_profile_code}; plan={result.plan_slug}"
                )
            if not write:
                transaction.set_rollback(True)

        summary = (
            f"Tenant seed reconciliation complete: {len(schools)} school(s), "
            f"{changed} would change."
        )
        if write:
            summary = (
                f"Tenant seed reconciliation written: {len(schools)} school(s), "
                f"{changed} changed."
            )
            self.stdout.write(self.style.SUCCESS(summary))
        else:
            self.stdout.write(self.style.WARNING(summary + " Re-run with --write to persist."))
