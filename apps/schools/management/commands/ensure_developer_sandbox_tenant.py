"""Provision or refresh the public developer sandbox tenant (demo-school)."""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.schools.marketing_settings_helpers import derive_marketing_demo_tenant_url


class Command(BaseCommand):
    help = "Ensure demo-school sandbox tenant exists for developer portal workflows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-slug",
            default="demo-school",
            help="Sandbox tenant slug (default: demo-school).",
        )

    def handle(self, *args, **options):
        slug = (options.get("school_slug") or "demo-school").strip()
        call_command("ensure_demo_environment", school_slug=slug)
        url = derive_marketing_demo_tenant_url("", slug, "runmycampus.com")
        self.stdout.write(self.style.SUCCESS(f"developer sandbox ready slug={slug}"))
        if url:
            self.stdout.write(f"tenant_url={url}")
