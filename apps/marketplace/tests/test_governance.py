import os
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.marketplace.models import (
    AppAuditLog,
    AppInstallation,
    MarketplaceApp,
    MarketplaceListing,
    MarketplaceReview,
    PublisherOrganization,
)
from apps.marketplace.services import install_app, submit_marketplace_review
from apps.schools.models import School
from apps.schools.tests.manager_client import login_manager_control_plane


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketplaceGovernanceTests(TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()
        self.manager = User.objects.create_superuser(
            username="marketplace-manager",
            email="marketplace-manager@example.com",
            password="pass1234",
        )
        self.school = School.objects.create(
            name="Marketplace School",
            slug="marketplace-school",
            subdomain="marketplace-school",
            is_active=True,
        )
        self.publisher = PublisherOrganization.objects.create(
            slug="verified-publisher",
            name="Verified Publisher",
            legal_name="Verified Publisher LLC",
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
            country_code="US",
            payout_ref="verified-publisher",
        )
        self.third_party_app = MarketplaceApp.objects.create(
            publisher=self.publisher,
            slug="attendance-pro",
            name="Attendance Pro",
            description="Third-party attendance analytics",
            kind=MarketplaceApp.AppKind.THIRD_PARTY,
            version="1.0.0",
            manifest={"widgets": {"attendance-overview": {"placement": "dashboard"}}},
            is_active=True,
            is_intentionally_free=True,
        )

    def tearDown(self):
        self.env.stop()

    def test_install_app_audit_includes_impact_snapshot(self):
        MarketplaceListing.objects.create(
            app=self.third_party_app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.APPROVED,
            security_review_status=MarketplaceListing.ReviewStatus.APPROVED,
        )
        install_app(
            self.school,
            self.third_party_app,
            installed_by=self.manager,
            run_schema_patches=False,
        )
        log = AppAuditLog.objects.filter(
            action="install", app=self.third_party_app
        ).first()
        self.assertIsNotNone(log)
        snap = (log.payload or {}).get("impact_snapshot") or {}
        self.assertIn("dependency_graph", snap)
        self.assertIn("compatibility", snap)
        self.assertIn("scopes_count", snap)

    def test_install_blocks_unapproved_third_party_listing(self):
        MarketplaceListing.objects.create(
            app=self.third_party_app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.PENDING_REVIEW,
            security_review_status=MarketplaceListing.ReviewStatus.APPROVED,
        )

        with self.assertRaisesMessage(ValueError, "not approved for install"):
            install_app(self.school, self.third_party_app, installed_by=self.manager)

    def test_governance_console_renders_on_manager_host(self):
        listing = MarketplaceListing.objects.create(
            app=self.third_party_app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.PENDING_REVIEW,
            security_review_status=MarketplaceListing.ReviewStatus.PENDING,
        )
        submit_marketplace_review(
            listing,
            review_type=MarketplaceReview.ReviewType.SECURITY,
            requested_by=self.manager,
            notes="Security review queued",
        )
        self.client.force_login(self.manager)

        response = self.client.get(
            reverse("super:marketplace_governance"), HTTP_HOST="manager.runmycampus.com"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Marketplace governance")
        self.assertContains(response, "Pending reviews")
        self.assertContains(response, self.third_party_app.name)

    def test_review_action_approves_listing(self):
        listing = MarketplaceListing.objects.create(
            app=self.third_party_app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.DRAFT,
            security_review_status=MarketplaceListing.ReviewStatus.APPROVED,
        )
        review = submit_marketplace_review(
            listing,
            review_type=MarketplaceReview.ReviewType.LISTING,
            requested_by=self.manager,
            notes="Ready for operator review",
        )
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("super:marketplace_review_action", args=[review.pk]),
            {"action": "approve", "notes": "Listing approved for install"},
            HTTP_HOST="manager.runmycampus.com",
        )

        self.assertEqual(response.status_code, 200)
        review.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(review.status, MarketplaceReview.Status.APPROVED)
        self.assertEqual(listing.status, MarketplaceListing.Status.APPROVED)
        self.assertFalse(listing.kill_switch_active)
        self.assertIsNotNone(listing.approved_at)

    def test_control_plane_catalog_installs_to_sandbox(self):
        MarketplaceListing.objects.create(
            app=self.third_party_app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.APPROVED,
            security_review_status=MarketplaceListing.ReviewStatus.APPROVED,
        )
        # Manager host reads the manager-named session cookie; force_login only
        # writes the default cookie, so the install POST would be anonymous (200
        # via follow to login) and create nothing. Bind the manager session.
        login_manager_control_plane(self.client, self.manager, password="pass1234")

        response = self.client.post(
            reverse("super:app_catalog"),
            {
                "app_id": self.third_party_app.pk,
                "school_id": self.school.pk,
                "install_after_impact_preview": "1",
            },
            HTTP_HOST="manager.runmycampus.com",
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        installation = AppInstallation.objects.get(
            app=self.third_party_app, school=self.school
        )
        self.assertEqual(
            installation.install_phase, AppInstallation.InstallPhase.SANDBOX
        )

    def test_catalog_install_blocked_without_impact_preview_ack(self):
        MarketplaceListing.objects.create(
            app=self.third_party_app,
            publisher=self.publisher,
            status=MarketplaceListing.Status.APPROVED,
            security_review_status=MarketplaceListing.ReviewStatus.APPROVED,
        )
        self.client.force_login(self.manager)
        self.client.post(
            reverse("super:app_catalog"),
            {"app_id": self.third_party_app.pk, "school_id": self.school.pk},
            HTTP_HOST="manager.runmycampus.com",
        )
        self.assertFalse(
            AppInstallation.objects.filter(
                app=self.third_party_app, school=self.school
            ).exists()
        )
