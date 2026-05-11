"""
Pass 14.D: provision an isolated sandbox tenant for app developer testing.

Each first-party / third-party app needs its own throw-away tenant where the
developer can install + uninstall their app, hammer the API, and break things
without affecting real schools. This command spins one up.

Reuses the existing provisioning pipeline (apps.schools.tasks._do_provision)
via the public synchronous helper so the sandbox tenant matches a real tenant
in every other way except its `is_sandbox=True` flag and the `<slug>-sandbox`
naming convention.

Run from the publisher dashboard backend (future UI lands separately) or
manually:

  python manage.py create_sandbox_tenant --publisher acme-co --owner-email dev@acme.test
  python manage.py create_sandbox_tenant --publisher acme-co --owner-email dev@acme.test --dry-run
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Provision an isolated sandbox School tenant for marketplace app developers. "
        "Idempotent — re-runs return the existing sandbox if one exists for the publisher."
    )

    def add_arguments(self, parser):
        parser.add_argument("--publisher", required=True, help="PublisherOrganization slug.")
        parser.add_argument(
            "--owner-email",
            required=True,
            help="Email of the developer admin for the sandbox.",
        )
        parser.add_argument(
            "--country",
            default="US",
            help="ISO-2 country code for the sandbox tenant (default: US).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing.",
        )

    def handle(self, *args, **options):
        publisher_slug = options["publisher"].strip().lower()
        owner_email = options["owner_email"].strip().lower()
        country = options["country"].strip().upper()[:2] or "US"
        dry_run = bool(options.get("dry_run"))

        try:
            from apps.marketplace.models import PublisherOrganization
            from apps.schools.models import School
        except ImportError as exc:
            self.stderr.write(self.style.ERROR(f"Required model missing: {exc}"))
            return

        publisher = PublisherOrganization.objects.filter(slug=publisher_slug).first() if hasattr(
            PublisherOrganization, "slug"
        ) else PublisherOrganization.objects.filter(name__iexact=publisher_slug).first()
        if not publisher:
            self.stderr.write(self.style.ERROR(f"Publisher '{publisher_slug}' not found."))
            return

        sandbox_slug = f"{publisher_slug}-sandbox"[:60]
        existing = School.objects.filter(slug=sandbox_slug).first()
        if existing:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sandbox already exists: {existing.name} (id={existing.id}, slug={existing.slug})"
                )
            )
            return

        if dry_run:
            self.stdout.write(
                f"Would create School(slug={sandbox_slug!r}, name='{publisher.name} Sandbox', "
                f"country={country!r}, is_active=True), plus admin user {owner_email!r}, "
                f"plus provisioning."
            )
            return

        school = School.objects.create(
            name=f"{publisher.name} Sandbox",
            slug=sandbox_slug,
            subdomain=sandbox_slug,
            country_code=country,
            is_active=False,
            is_approved=True,
            settings={
                "is_sandbox": True,
                "sandbox_publisher_id": publisher.pk,
                "sandbox_expires_at": (timezone.now() + timedelta(days=90)).isoformat(),
            },
        )

        # Create the developer admin user.
        User = get_user_model()
        admin_user, created = User.objects.get_or_create(
            email=owner_email,
            defaults={
                "username": owner_email.split("@")[0][:150],
                "role": User.Role.ADMIN,
                "is_active": True,
                "is_staff": True,
            },
        )
        if created:
            admin_user.set_password(secrets.token_urlsafe(24))
            admin_user.save()

        # Reuse the existing provisioning pipeline so the sandbox looks just
        # like a real tenant minus the is_sandbox flag.
        try:
            from apps.schools.tasks import provision_school_sync

            provision_school_sync(str(school.id), contact_email=owner_email)
        except (ImportError, AttributeError, TypeError, ValueError) as exc:
            self.stderr.write(
                self.style.WARNING(
                    f"School created but provisioning raised: {exc}. "
                    f"Run `provision_school_sync {school.id} {owner_email}` manually."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Sandbox provisioned: {school.name} (id={school.id}, slug={school.slug}). "
                f"Admin: {owner_email}. Expires in 90 days."
            )
        )
