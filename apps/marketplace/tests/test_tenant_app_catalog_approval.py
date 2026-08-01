from pathlib import Path
import uuid

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.marketplace.manifest_schema import (
    compatibility_signals_for_listing,
    normalize_platform_manifest,
    platform_compatibility_version,
)
from apps.marketplace.models import MarketplaceApp, MarketplaceListing, PublisherOrganization
from apps.marketplace.services import check_app_compatibility
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models_platform_catalog import Plan


ROOT = Path(__file__).resolve().parents[3]
HOST = "catalog-approval.runmycampus.com"


class TenantAppCatalogApprovalSourceTests(SimpleTestCase):
    def test_approved_catalog_structure_replaces_legacy_proof_hero(self):
        template = (ROOT / "templates/marketplace/tenant_app_catalog.html").read_text(
            encoding="utf-8"
        )
        for marker in (
            "rmc-catalog-readiness-grid",
            "Install readiness",
            "data-rmc-catalog-filter-form",
            "rmc-catalog-app-grid",
            "Compatibility & rollback",
            "Review & install",
        ):
            self.assertIn(marker, template)
        self.assertNotIn('class="proof-hero"', template)
        self.assertNotIn("rmc-catalog-app rmc-reveal", template)
        self.assertNotIn("data-catalog-api-url", template)
        self.assertNotIn("listing.preview_image_url", template)
        self.assertNotIn("style=", template)

        policy_partial = (
            ROOT / "templates/partials/shell_chrome_marketplace_tenant_ops_strip.html"
        ).read_text(encoding="utf-8")
        self.assertIn("Your operating policy", policy_partial)

        nav_source = (
            ROOT / "apps/platform_runtime/operational_center_nav.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Governed capability marketplace", nav_source)

        stylesheet = (
            ROOT / "static/css/marketplace-tenant-app-catalog.css"
        ).read_text(encoding="utf-8")
        self.assertIn("--text-primary: var(--color-base-50, #f8fafc)", stylesheet)
        self.assertIn("--rmc-catalog-ink: var(--color-base-50, #f8fafc)", stylesheet)

    def test_filter_controller_never_replaces_governed_server_cards(self):
        controller = (ROOT / "static/js/tenant-app-catalog.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("requestSubmit", controller)
        self.assertNotIn("fetch(", controller)
        self.assertNotIn("replaceChildren", controller)
        self.assertNotIn("createElement", controller)


@override_settings(APP_VERSION="3.2.1", RMC_RELEASE_VERSION="2026.08")
class TenantAppCatalogCompatibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            slug="sovereign-self-hosted", name="Sovereign / Self-Hosted"
        )
        cls.school = School.objects.create(
            name="Gilead Compatibility",
            slug="gilead-compatibility",
            subdomain="gilead-compatibility",
            is_active=True,
            plan=cls.plan,
        )
        cls.publisher = PublisherOrganization.objects.create(
            slug="catalog-approval-publisher",
            name="Catalog Approval Publisher",
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
        )
        cls.app = MarketplaceApp.objects.create(
            slug="catalog-approval-app",
            name="Catalog Approval App",
            version="1.0.0",
            publisher=cls.publisher,
            manifest={},
            is_intentionally_free=True,
        )
        cls.listing = MarketplaceListing.objects.create(
            app=cls.app,
            publisher=cls.publisher,
            status=MarketplaceListing.Status.APPROVED,
            compatibility={
                "plan_tiers": ["standard", "enterprise"],
                "min_rmc_version": "2025.03",
            },
        )

    def test_sovereign_plan_matches_enterprise_manifest_tier(self):
        ok, warnings, errors = check_app_compatibility(
            self.school, self.app, warn_only=True
        )
        self.assertTrue(ok)
        self.assertEqual(warnings, [])
        self.assertEqual(errors, [])

    def test_current_pro_plan_alias_matches_legacy_standard_manifest_tier(self):
        pro_plan = Plan.objects.create(slug="growing-school", name="Growing School")
        pro_school = School.objects.create(
            name="Growing Compatibility",
            slug="growing-compatibility",
            subdomain="growing-compatibility",
            is_active=True,
            plan=pro_plan,
        )
        ok, warnings, errors = check_app_compatibility(
            pro_school, self.app, warn_only=True
        )
        self.assertTrue(ok)
        self.assertEqual(warnings, [])
        self.assertEqual(errors, [])

    def test_calendar_release_floor_uses_calendar_release_not_product_semver(self):
        self.assertEqual(platform_compatibility_version("2025.03"), "2026.08")
        self.assertEqual(platform_compatibility_version("3.0.0"), "3.2.1")
        manifest = normalize_platform_manifest(
            self.app.manifest,
            app_slug=self.app.slug,
            app_name=self.app.name,
            version=self.app.version,
            publisher_slug=self.publisher.slug,
        )
        signals = compatibility_signals_for_listing(
            self.school, self.listing, manifest
        )
        self.assertTrue(signals["ok"], signals["messages"])
        self.assertEqual(signals["messages"], [])

    @override_settings(RMC_RELEASE_VERSION="2024.12")
    def test_genuine_outdated_calendar_release_is_still_blocked(self):
        manifest = normalize_platform_manifest(
            self.app.manifest,
            app_slug=self.app.slug,
            app_name=self.app.name,
            version=self.app.version,
            publisher_slug=self.publisher.slug,
        )
        signals = compatibility_signals_for_listing(
            self.school, self.listing, manifest
        )
        self.assertFalse(signals["ok"])
        self.assertIn(
            "Platform version 2024.12 is below listing minimum RMC 2025.03.",
            signals["messages"],
        )


@override_settings(ALLOWED_HOSTS=["testserver", HOST])
class TenantAppCatalogFilterIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(slug="enterprise", name="Enterprise")
        cls.school = School.objects.create(
            name="Catalog Approval School",
            slug="catalog-approval",
            subdomain="catalog-approval",
            is_active=True,
            plan=cls.plan,
        )
        cls.publisher = PublisherOrganization.objects.create(
            slug="filter-publisher",
            name="Filter Publisher",
            verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
        )
        for slug, name, category in (
            ("approval-admissions", "Admissions Lead Tracker", "Admissions"),
            ("approval-analytics", "Advanced Analytics Pack", "Analytics"),
        ):
            app = MarketplaceApp.objects.create(
                slug=slug,
                name=name,
                version="1.0.0",
                publisher=cls.publisher,
                manifest={},
                is_intentionally_free=True,
            )
            MarketplaceListing.objects.create(
                app=app,
                publisher=cls.publisher,
                category=category,
                status=MarketplaceListing.Status.APPROVED,
                compatibility={"plan_tiers": ["enterprise"]},
            )

    def _client(self):
        user = User.objects.create_user(
            username=f"catalog_admin_{uuid.uuid4().hex[:8]}",
            password="catalog-password",
            role=User.Role.ADMIN,
        )
        TeacherProfile.objects.create(user=user, school=self.school, staff_id="CAT-1")
        SchoolMembership.objects.create(
            user=user, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        TOTPDevice.objects.create(user=user, name="test-device", confirmed=True)
        client = Client(HTTP_HOST=HOST)
        client.login(username=user.username, password="catalog-password")
        session = client.session
        session["mfa_verified"] = True
        session.save()
        return client

    def test_server_owned_filters_preserve_real_install_actions(self):
        response = self._client().get(
            reverse("tenant_app_catalog", urlconf="config.tenant_urls"),
            {"q": "analytics", "outcome": "Analytics", "sort": "rating"},
        )
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertContains(response, "Advanced Analytics Pack")
        self.assertNotContains(response, "Admissions Lead Tracker")
        self.assertContains(response, "data-rmc-open-install-impact")
        self.assertContains(response, 'data-rmc-catalog-filter-form="1"')
        self.assertContains(response, 'value="analytics"')
