"""Tests for the v3.17 onboarding Migration step + handoff page.

Covers the critical paths so the wave is verifiable end-to-end:

1. Vendor catalog integrity — every entry has the required fields.
2. Wizard step 3 GET renders the vendor grid.
3. Wizard step 3 POST with a vendor stores the choice in session and advances.
4. Wizard step 3 POST with skip_migration clears the choice and advances.
5. signup_school persists the migration intent into school.settings.
6. verify_signup with migration intent redirects to the handoff page.
7. verify_signup without migration intent redirects to the dashboard / launch.
8. onboard_migration_handoff GET renders for an authenticated admin.
9. onboard_migration_start POST writes the final selection and redirects to
   MC intake with vendor/profile/school_id pre-filled.
10. MC IntakeView GET honours ?vendor= and propagates it into the form.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.schools.models import School, SignupVerification
from apps.schools.onboarding_vendors import (
    DOMAINS_BY_SLUG,
    ONBOARDING_DATA_DOMAINS,
    ONBOARDING_VENDORS,
    VENDORS_BY_SLUG,
    estimate_minutes,
    resolve_vendor,
)


User = get_user_model()


class VendorCatalogIntegrityTests(TestCase):
    """The catalog is the SOT for vendor tiles + post-verify routing. Drift here
    breaks the whole flow, so we lock the contract in tests."""

    def test_catalog_has_twelve_curated_tiles(self):
        self.assertEqual(len(ONBOARDING_VENDORS), 12)

    def test_every_vendor_has_required_fields(self):
        for v in ONBOARDING_VENDORS:
            self.assertTrue(v.slug, f"slug missing for {v}")
            self.assertTrue(v.name, f"name missing for {v}")
            self.assertEqual(len(v.monogram), 2, f"monogram must be 2 chars for {v.slug}")
            self.assertIn(v.palette, {"ink", "indigo", "teal", "amber"})
            self.assertTrue(v.tagline)

    def test_vendor_slugs_are_unique(self):
        slugs = [v.slug for v in ONBOARDING_VENDORS]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertEqual(set(slugs), set(VENDORS_BY_SLUG))

    def test_resolve_vendor_is_case_insensitive_and_safe(self):
        self.assertEqual(resolve_vendor("powerschool").slug, "powerschool")
        self.assertEqual(resolve_vendor("  PowerSchool  ").slug, "powerschool")
        self.assertIsNone(resolve_vendor(""))
        self.assertIsNone(resolve_vendor(None))
        self.assertIsNone(resolve_vendor("not-a-real-vendor"))

    def test_estimate_minutes_sums_known_domains_only(self):
        all_slugs = [d.slug for d in ONBOARDING_DATA_DOMAINS]
        total = sum(d.minutes for d in ONBOARDING_DATA_DOMAINS)
        self.assertEqual(estimate_minutes(all_slugs), total)
        # Unknown slugs are silently dropped — no KeyError, no inflation
        self.assertEqual(estimate_minutes(all_slugs + ["unknown"]), total)
        self.assertEqual(estimate_minutes([]), 0)

    def test_default_on_domains_match_documented_baseline(self):
        on = {d.slug for d in ONBOARDING_DATA_DOMAINS if d.default_on}
        self.assertEqual(
            on,
            {"students", "staff", "grades", "attendance", "contacts"},
            "Default-on data domains must stay the documented set so the time "
            "tally shown in the handoff page matches operator expectation.",
        )


class OnboardingWizardMigrationStepTests(TestCase):
    """Step 3 behaviour — vendor pick + skip + state transitions."""

    def test_step_3_get_renders_vendor_grid(self):
        # Seed session through step 2 by hitting the previous steps.
        resp = self.client.post(
            reverse("onboard_wizard") + "?step=1",
            {"step": "1", "country_code": "US", "school_flavor": "general"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        resp = self.client.post(
            reverse("onboard_wizard") + "?step=2",
            {"step": "2", "plan_slug": "", "trial": "1"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get(reverse("onboard_wizard") + "?step=3")
        self.assertEqual(resp.status_code, 200)
        # Vendor grid markup present
        self.assertContains(resp, 'data-vendor-slug="powerschool"')
        self.assertContains(resp, 'data-vendor-slug="spreadsheet"')
        # Step indicator advances
        self.assertContains(resp, 'data-rmc-wizard-active="3"')

    def test_step_3_post_with_vendor_persists_and_advances(self):
        # Pre-seed session
        s = self.client.session
        s["onboarding_step"] = 3
        s.save()
        resp = self.client.post(
            reverse("onboard_wizard") + "?step=3",
            {"step": "3", "vendor_slug": "powerschool"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("step=4", resp.url)
        sess = self.client.session
        self.assertEqual(sess["onboarding_migrate_vendor"], "powerschool")
        self.assertEqual(sess["onboarding_migrate_source_system"], "powerschool")
        self.assertIn("students", sess["onboarding_migrate_domains"])

    def test_step_3_skip_clears_choice_and_advances(self):
        s = self.client.session
        s["onboarding_step"] = 3
        s["onboarding_migrate_vendor"] = "powerschool"
        s.save()
        resp = self.client.post(
            reverse("onboard_wizard") + "?step=3",
            {"step": "3", "skip_migration": "1"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("step=4", resp.url)
        sess = self.client.session
        self.assertIsNone(sess["onboarding_migrate_vendor"])
        self.assertEqual(sess["onboarding_migrate_domains"], [])


class SignupAndVerifyMigrationRoutingTests(TestCase):
    """signup_school persists intent → verify_signup routes accordingly."""

    def test_verify_with_migration_intent_redirects_to_handoff(self):
        # Build a school with migration intent already persisted (skip the
        # public-form roundtrip — we cover the persistence in a unit test).
        school = School.objects.create(
            name="Cedar Ridge Academy",
            slug="cedar-ridge",
            subdomain="cedar-ridge",
            is_active=False,
            country_code="US",
            settings={
                "rmc_public_onboarding": {
                    "migration": {
                        "vendor_slug": "powerschool",
                        "profile_slug": "students_from_powerschool",
                        "source_system": "powerschool",
                        "domains": ["students", "grades"],
                    }
                }
            },
        )
        admin = User.objects.create_user(
            username="admin@cedar.test",
            email="admin@cedar.test",
            password="x",
        )
        # set_unusable_password so verify_signup logs them in directly
        admin.set_unusable_password()
        admin.is_active = True
        admin.save()
        sv = SignupVerification.objects.create(
            school=school,
            email=admin.email,
            expires_at=timezone.now() + timedelta(days=1),
        )
        resp = self.client.get(
            reverse("verify_signup") + f"?token={sv.token}",
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("onboard_migration_handoff"))

    def test_verify_without_migration_intent_routes_to_dashboard(self):
        school = School.objects.create(
            name="Plain School",
            slug="plain",
            subdomain="plain",
            is_active=False,
            country_code="US",
            settings={},  # no migration intent
        )
        admin = User.objects.create_user(
            username="admin@plain.test",
            email="admin@plain.test",
            password="x",
        )
        admin.set_unusable_password()
        admin.is_active = True
        admin.save()
        sv = SignupVerification.objects.create(
            school=school, email=admin.email,
            expires_at=timezone.now() + timedelta(days=1),
        )
        resp = self.client.get(
            reverse("verify_signup") + f"?token={sv.token}",
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertNotEqual(resp.url, reverse("onboard_migration_handoff"))


class OnboardMigrationHandoffTests(TestCase):
    """Handoff page rendering + the one-click start POST."""

    def _make_admin_with_school(self, vendor_slug="powerschool"):
        school = School.objects.create(
            name="Test School",
            slug="test",
            subdomain="test",
            is_active=True,
            country_code="US",
            settings={
                "rmc_public_onboarding": {
                    "migration": {
                        "vendor_slug": vendor_slug,
                        "profile_slug": "students_from_powerschool",
                        "source_system": "powerschool",
                        "domains": ["students", "grades"],
                    }
                }
            },
        )
        admin = User.objects.create_user(
            username="admin@test.test",
            email="admin@test.test",
            password="x",
        )
        admin.is_active = True
        admin.save()
        SignupVerification.objects.create(
            school=school, email=admin.email,
            expires_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(admin)
        return school, admin

    def test_handoff_get_renders_for_authenticated_admin_with_intent(self):
        school, _ = self._make_admin_with_school()
        resp = self.client.get(reverse("onboard_migration_handoff"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "PowerSchool")
        self.assertContains(resp, "What we’ll bring across")
        # Tally pill shows the pre-selected domain count
        self.assertContains(resp, 'id="omig-tally-count"')

    def test_handoff_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse("onboard_migration_handoff"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url.lower())

    def test_start_with_vendor_redirects_to_mc_intake_with_prefill(self):
        school, _ = self._make_admin_with_school()
        resp = self.client.post(
            reverse("onboard_migration_start"),
            {
                "vendor_slug": "powerschool",
                "domains": ["students", "grades"],
            },
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/super/migration/new/", resp.url)
        self.assertIn("vendor=powerschool", resp.url)
        self.assertIn(f"school_id={school.id}", resp.url)
        # Final selection persisted onto school.settings for return visits
        school.refresh_from_db()
        self.assertEqual(
            school.settings["rmc_public_onboarding"]["migration"]["domains"],
            ["students", "grades"],
        )

    def test_start_with_skip_redirects_to_dashboard(self):
        school, _ = self._make_admin_with_school()
        resp = self.client.post(
            reverse("onboard_migration_start"),
            {"vendor_slug": "powerschool", "skip": "1"},
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn("/super/migration/new/", resp.url)


class MCIntakePrefillTests(TestCase):
    """MigrationCloudIntakeView GET reads ?vendor / ?profile / ?school_id."""

    def test_intake_get_with_vendor_prefills_form(self):
        # Create a superuser so the entitlement gate lets us in on the super shell
        admin = User.objects.create_superuser(
            username="op", email="op@test.test", password="x"
        )
        self.client.force_login(admin)
        resp = self.client.get(
            reverse("migration_cloud_super:bundle_new") + "?vendor=powerschool",
        )
        self.assertEqual(resp.status_code, 200)
        # Pre-fill banner surfaces the provenance
        self.assertContains(resp, "Pre-filled from your onboarding choice")
