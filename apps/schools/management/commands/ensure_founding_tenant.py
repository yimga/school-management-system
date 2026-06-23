"""Ensure the env-configured founding/bootstrap tenant row exists.

Replaces reliance on migration-seeded founding-school slugs for new installs.
Does NOT edit applied migrations — idempotent ``get_or_create`` only.

Env (7-layer cascade, highest wins):
  DEFAULT_TENANT_SLUG       (default: demo-school)
  DEFAULT_TENANT_NAME       (default: derived from slug)
  DEFAULT_TENANT_SUBDOMAIN  (default: slug)

Production: runs when ``DEFAULT_TENANT_*`` is set OR ``--force`` is passed.
Development (DEBUG): always runs so local ``manage.py runserver`` has a tenant.

Example:
  DEFAULT_TENANT_SLUG=demo-school python manage.py ensure_founding_tenant --link-admin
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.schools.founding_tenant_defaults import (
    founding_tenant_env_explicit,
    resolve_founding_tenant_name,
    resolve_founding_tenant_slug,
    resolve_founding_tenant_subdomain,
)
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Ensure the DEFAULT_TENANT_* bootstrap school row exists (idempotent). "
        "Links platform admin when --link-admin is set."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--slug",
            default="",
            help="Override DEFAULT_TENANT_SLUG for this invocation.",
        )
        parser.add_argument(
            "--name",
            default="",
            help="Override DEFAULT_TENANT_NAME for this invocation.",
        )
        parser.add_argument(
            "--subdomain",
            default="",
            help="Override DEFAULT_TENANT_SUBDOMAIN for this invocation.",
        )
        parser.add_argument(
            "--link-admin",
            action="store_true",
            help="Link the platform 'admin' superuser to this tenant (SchoolMembership).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even in production when DEFAULT_TENANT_* env is unset.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the resolved bootstrap target without writing.",
        )

    def handle(self, *args, **options):
        if not (
            settings.DEBUG
            or options.get("force")
            or founding_tenant_env_explicit()
            or (options.get("slug") or "").strip()
        ):
            self.stdout.write(
                self.style.WARNING(
                    "Skipping ensure_founding_tenant (set DEFAULT_TENANT_SLUG/NAME/SUBDOMAIN, "
                    "use --force, or run with DEBUG=True)."
                )
            )
            return

        slug_override = (options.get("slug") or "").strip() or None
        name_override = (options.get("name") or "").strip() or None
        sub_override = (options.get("subdomain") or "").strip() or None

        try:
            slug = resolve_founding_tenant_slug(override=slug_override)
            name = resolve_founding_tenant_name(slug=slug, override=name_override)
            subdomain = resolve_founding_tenant_subdomain(
                slug=slug, override=sub_override
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if options.get("dry_run"):
            self.stdout.write(
                f"founding tenant dry-run slug={slug} name={name!r} subdomain={subdomain}"
            )
            return

        with transaction.atomic():
            school, created = School.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "subdomain": subdomain,
                    "sub_system": "EN",
                    "is_active": True,
                    "is_approved": True,
                },
            )
            updates: list[str] = []
            if school.name != name:
                school.name = name
                updates.append("name")
            if (school.subdomain or "").strip() != subdomain:
                school.subdomain = subdomain
                updates.append("subdomain")
            if not school.is_active:
                school.is_active = True
                updates.append("is_active")
            if not school.is_approved:
                school.is_approved = True
                updates.append("is_approved")
            if updates:
                updates.append("updated_at")
                school.save(update_fields=updates)

        verb = "created" if created else "ensured"
        self.stdout.write(
            self.style.SUCCESS(
                f"Founding tenant {verb}: slug={school.slug} id={school.pk} name={school.name!r}"
            )
        )

        if options.get("link_admin"):
            user = User.objects.filter(username="admin").first()
            if not user:
                self.stdout.write(
                    self.style.WARNING(
                        "Platform user 'admin' not found; run ensure_superuser first."
                    )
                )
                return
            membership, mem_created = SchoolMembership.objects.get_or_create(
                user=user,
                school=school,
                defaults={"role": "ADMIN", "is_primary": True},
            )
            if membership.role != "ADMIN" or not membership.is_primary:
                membership.role = "ADMIN"
                membership.is_primary = True
                membership.save(update_fields=["role", "is_primary"])
            if mem_created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Linked admin -> {school.slug} (SchoolMembership created)."
                    )
                )
