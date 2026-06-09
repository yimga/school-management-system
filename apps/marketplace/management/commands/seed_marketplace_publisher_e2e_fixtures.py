"""Seed deterministic marketplace publisher-install E2E fixtures."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Permission
from apps.marketplace.models import MarketplaceReview
from apps.marketplace.services import upsert_marketplace_submission
from apps.schools.models import School, SchoolMembership


class Command(BaseCommand):
    help = (
        "Create e2e-mkt-install tenant + pending publisher review for Playwright "
        "marketplace publisher-install spec."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant-password",
            default="E2eMktInstall!RmC9",
            help="Tenant admin password.",
        )
        parser.add_argument(
            "--app-slug",
            default="e2e-install-widget",
            help="Marketplace app slug under review.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        tenant_password = options["tenant_password"]
        app_slug = options["app_slug"]
        tenant_slug = "e2e-mkt-install"
        tenant_email = "e2e-mkt-admin@runmycampus.test"
        publisher_email = "e2e-mkt-publisher@runmycampus.test"

        school, _ = School.objects.get_or_create(
            slug=tenant_slug,
            defaults={
                "name": "E2E Marketplace Install School",
                "subdomain": tenant_slug,
                "is_active": True,
            },
        )
        school.is_active = True
        school.save(update_fields=["is_active", "updated_at"])

        tenant_admin, _ = User.objects.get_or_create(
            username=tenant_email,
            defaults={"email": tenant_email, "role": User.Role.ADMIN},
        )
        tenant_admin.email = tenant_email
        tenant_admin.role = User.Role.ADMIN
        tenant_admin.set_password(tenant_password)
        tenant_admin.save()

        perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        tenant_admin.feature_permissions.add(perm)

        SchoolMembership.objects.get_or_create(
            user=tenant_admin,
            school=school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )

        publisher_user, _ = User.objects.get_or_create(
            username=publisher_email,
            defaults={"email": publisher_email, "role": User.Role.ADMIN},
        )
        publisher_user.email = publisher_email
        publisher_user.set_password("E2eMktPublisher!RmC9")
        publisher_user.save()

        from apps.marketplace.models import PublisherOrganization

        PublisherOrganization.objects.get_or_create(
            slug="e2e-mkt-publisher",
            defaults={
                "name": "E2E Marketplace Publisher",
                "verified_contact_email": publisher_email,
                "verification_status": PublisherOrganization.VerificationStatus.VERIFIED,
            },
        )

        result = upsert_marketplace_submission(
            user=publisher_user,
            payload={
                "slug": app_slug,
                "name": "E2E Install Widget",
                "version": "1.0.0",
                "kind": "third_party",
                "manifest": {"scopes": ["students:read"]},
            },
        )
        review_id = result.get("review_id")
        review_status = ""
        if review_id:
            review_status = MarketplaceReview.objects.get(pk=review_id).status

        self.stdout.write(
            self.style.SUCCESS(
                "marketplace-e2e ready "
                f"tenant={tenant_slug} admin={tenant_email} "
                f"app={app_slug} review_id={review_id} review_status={review_status}"
            )
        )
