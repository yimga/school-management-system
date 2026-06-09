"""Publisher submit → operator approve → tenant install (service layer E2E)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.marketplace.models import AppInstallation, MarketplaceReview
from apps.marketplace.partner_submission import approve_partner_submission
from apps.marketplace.services import install_app, upsert_marketplace_submission
from apps.schools.models import School


class PublisherInstallE2EFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.publisher_user = User.objects.create_user(
            username="install-pub@example.com",
            email="install-pub@example.com",
            password="Test1234!",
        )
        self.operator = User.objects.create_superuser(
            username="install-op",
            email="install-op@example.com",
            password="Test1234!",
        )
        self.school = School.objects.create(
            name="Install E2E School",
            slug="install-e2e",
            subdomain="install-e2e",
            is_active=True,
        )
        from apps.marketplace.models import PublisherOrganization

        PublisherOrganization.objects.create(
            slug="install-publisher",
            name="Install Publisher",
            verified_contact_email="install-pub@example.com",
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
        )

    def test_submit_approve_install_on_tenant(self) -> None:
        result = upsert_marketplace_submission(
            user=self.publisher_user,
            payload={
                "slug": "install-widget",
                "name": "Install Widget",
                "version": "1.0.0",
                "kind": "third_party",
                "manifest": {"scopes": ["students:read"]},
            },
        )
        review = MarketplaceReview.objects.get(pk=result["review_id"])
        self.assertEqual(review.review_type, MarketplaceReview.ReviewType.SECURITY)

        approve_partner_submission(review, approved_by=self.operator, notes="ok for e2e")

        from apps.marketplace.models import MarketplaceApp

        app = MarketplaceApp.objects.get(slug="install-widget")
        installation = install_app(
            self.school,
            app,
            installed_by=self.operator,
            run_schema_patches=False,
            grant_scope_codes=["students:read"],
        )
        self.assertTrue(
            AppInstallation.objects.filter(
                school=self.school, app=app, pk=installation.pk
            ).exists()
        )
