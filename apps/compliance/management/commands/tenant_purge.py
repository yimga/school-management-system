"""Tenant purge: archive + cascade-delete a tenant's data (CLI wrapper)."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

from apps.schools.models import School
from apps.schools.tenant_offboarding import (
    apply_purge,
    clear_purge_policy_blockers,
    dry_run_purge,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Archive + cascade-delete a tenant. Strict: requires --confirm-delete-string=<slug>."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            required=True,
            help="Tenant school slug (comma-separated for multiple).",
        )
        parser.add_argument(
            "--confirm-delete-string",
            required=True,
            help="Must match the school slug exactly (proof-of-intent guard).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually delete (default is dry-run inventory).",
        )
        parser.add_argument(
            "--force-provisioning",
            action="store_true",
            help="Allow purge while provisioning events are in-flight.",
        )
        parser.add_argument(
            "--override-policy",
            action="store_true",
            help=(
                "Test/dev only: clear legal hold and bypass dual-approval gates "
                "(also enables --force-provisioning)."
            ),
        )

    def handle(self, *args, **opts):
        slugs = [
            s.strip()
            for s in str(opts.get("school") or "").split(",")
            if s.strip()
        ]
        confirm = str(opts.get("confirm_delete_string") or "").strip()
        if not slugs:
            raise CommandError("--school is required")
        if len(slugs) == 1:
            if confirm != slugs[0]:
                raise CommandError(
                    "--confirm-delete-string must equal --school exactly (intent guard)"
                )
        else:
            expected = ",".join(slugs)
            if confirm != expected:
                raise CommandError(
                    "--confirm-delete-string must equal comma-separated --school "
                    f"list exactly: {expected!r}"
                )

        override_policy = bool(opts.get("override_policy"))
        for slug in slugs:
            self._purge_one_slug(
                slug,
                apply=bool(opts.get("apply")),
                force_provisioning=bool(opts.get("force_provisioning"))
                or override_policy,
                dual_approved=override_policy,
                override_policy=override_policy,
            )

    def _purge_one_slug(
        self,
        slug: str,
        *,
        apply: bool,
        force_provisioning: bool,
        dual_approved: bool = False,
        override_policy: bool = False,
    ) -> None:
        school = School.objects.filter(slug=slug).first()
        if school is None:
            raise CommandError(f"School slug not found: {slug!r}")

        if override_policy:
            state = clear_purge_policy_blockers(school, reason="tenant_purge_cli_override")
            self.stdout.write(
                self.style.WARNING(
                    f"[{slug}] Policy override: legal_hold={state['legal_hold_active']}, "
                    f"dual_approved={state['dual_approved']}"
                )
            )

        if not apply:
            preview = dry_run_purge(
                school,
                confirm_slug=slug,
                force_provisioning=force_provisioning,
                dual_approved=dual_approved,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{slug}] Inventory: {preview.row_total} total rows across "
                    f"{len(preview.inventory)} tenant-scoped models"
                )
            )
            self.stdout.write(f"[{slug}] Archive manifest: {preview.manifest_path}")
            if preview.purge_blocked_reasons:
                self.stdout.write(
                    self.style.WARNING(
                        f"[{slug}] Blockers: {', '.join(preview.purge_blocked_reasons)}"
                    )
                )
            self.stdout.write(
                self.style.WARNING(
                    f"[{slug}] DRY-RUN — re-run with --apply to execute the cascade delete."
                )
            )
            return

        try:
            receipt = apply_purge(
                school,
                actor=None,
                confirm_slug=slug,
                dry_run=False,
                force_provisioning=force_provisioning,
                dual_approved=dual_approved,
                purge_source="cli_override" if override_policy else "operator",
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"[{slug}] Deleted school {receipt.school_slug!r} (pk={receipt.school_id})."
            )
        )
        if receipt.schema_dropped:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{slug}] Dropped tenant schema: {receipt.schema_dropped}"
                )
            )
        self.stdout.write(f"[{slug}] Receipt manifest: {receipt.manifest_path}")
