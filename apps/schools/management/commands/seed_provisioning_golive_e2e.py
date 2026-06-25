"""Arm a tenant for provisioning → go-live Playwright (batch 1731 gap close)."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.schools.models import School
from apps.setup_studio.models import SetupProgress
from apps.setup_studio.services import compile_setup_studio, get_setup_studio_payload


class Command(BaseCommand):
    help = (
        "Reset launched_at and refresh Setup Studio launch_ready for Playwright go-live E2E. "
        "Run with runserver + SIGNUP_E2E_LOCAL_DNS_MAP=1."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--slug",
            default="demo-school",
            help="Tenant slug (default: demo-school).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        slug = (options.get("slug") or "demo-school").strip()
        school = School.objects.filter(slug=slug).first()
        if school is None:
            self.stderr.write(self.style.ERROR(f"School not found: {slug}"))
            return

        compile_setup_studio(school)
        payload = get_setup_studio_payload(school) or {}
        progress, _ = SetupProgress.objects.get_or_create(school=school)
        progress.launched_at = None
        progress.save(update_fields=["launched_at", "updated_at"])

        launch_ready = bool(payload.get("launch_ready"))
        blockers = payload.get("launch_blockers") or []
        self.stdout.write(
            self.style.SUCCESS(
                f"Armed {slug}: launch_ready={launch_ready} "
                f"blockers={len(blockers)} launched_at cleared"
            )
        )
        if not launch_ready:
            self.stdout.write(
                self.style.WARNING(
                    "Go-live Playwright test will skip until blockers clear. "
                    "Run ensure_demo_environment / academic year wizard, then re-run this command."
                )
            )
            for blocker in blockers[:5]:
                self.stdout.write(f"  blocker: {blocker}")
