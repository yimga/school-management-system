"""Provision or refresh the public developer sandbox tenant (demo-school)."""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.schools.marketing_settings_helpers import derive_marketing_demo_tenant_url
from apps.schools.models import School


def ensure_sandbox_school_row(slug: str) -> School:
    """Create or reactivate the sandbox School row before academic/demo seeding."""
    normalized = (slug or "").strip()
    if not normalized:
        raise ValueError("school slug is required")
    with transaction.atomic():
        school = School.objects.filter(slug=normalized).first()
        if school is None:
            school = School.objects.create(
                name=normalized.replace("-", " ").title(),
                slug=normalized,
                subdomain=normalized,
                is_active=True,
                is_approved=True,
            )
            return school
        changed: list[str] = []
        if not school.is_active:
            school.is_active = True
            changed.append("is_active")
        if not school.is_approved:
            school.is_approved = True
            changed.append("is_approved")
        if not (school.subdomain or "").strip():
            school.subdomain = normalized
            changed.append("subdomain")
        if changed:
            school.save(update_fields=changed)
        return school


class Command(BaseCommand):
    help = "Ensure demo-school sandbox tenant exists for developer portal workflows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-slug",
            default="demo-school",
            help="Sandbox tenant slug (default: demo-school).",
        )
        parser.add_argument(
            "--password",
            default="Test1234",
            help="Password for demo tenant users (default: Test1234).",
        )

    def handle(self, *args, **options):
        slug = (options.get("school_slug") or "demo-school").strip()
        password = (options.get("password") or "Test1234").strip()
        school = ensure_sandbox_school_row(slug)
        try:
            call_command(
                "ensure_demo_environment",
                school_slug=slug,
                password=password,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort academic seed; users still required for E2E
            self.stderr.write(
                self.style.WARNING(
                    f"ensure_demo_environment partial failure for {slug}: {exc!s}; "
                    "continuing with demo user seed only."
                )
            )
            call_command(
                "seed_demo_tenant_users",
                school_slug=slug,
                password=password,
            )
        url = derive_marketing_demo_tenant_url("", slug, "runmycampus.com")
        self.stdout.write(
            self.style.SUCCESS(
                f"developer sandbox ready slug={school.slug} id={school.pk}"
            )
        )
        if url:
            self.stdout.write(f"tenant_url={url}")
