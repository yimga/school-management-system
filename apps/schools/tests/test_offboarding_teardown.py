"""Offboarding teardown completeness: deactivation actually switches a tenant OFF.

Closes two audited gaps in ``apply_school_lifecycle_action``:
  * the custom domain kept resolving to a deactivated tenant (G1 — ABSENT), and
  * the billing subscription was never suspended on deactivate (G2 — PARTIAL).

Both are reversible (reactivation re-verifies the domain and resumes billing),
matching the platform's soft-delete philosophy.
"""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from apps.billing.models import BillingAccount, TenantSubscription
from apps.billing.services import ensure_subscription_for_school
from apps.schools.control_plane_lifecycle import (
    _target_subscription_status_for_school,
    apply_school_lifecycle_action,
)
from apps.schools.domain_unbind import unbind_custom_domains
from apps.schools.models import School, SchoolDomain
from apps.siteconfig.models import RegionConfig


class OffboardingTeardownTests(TestCase):
    def _make_school(self, slug: str, *, with_custom_domain: bool = True) -> School:
        school = School.objects.create(
            name=f"Teardown {slug}",
            slug=slug,
            subdomain=slug,
            is_active=True,
            is_approved=True,
            default_region=RegionConfig.get_default(),
            custom_domain="portal.example-school.edu" if with_custom_domain else "",
            custom_domain_verified=with_custom_domain,
        )
        if with_custom_domain:
            SchoolDomain.objects.create(
                school=school,
                domain="portal.example-school.edu",
                is_verified=True,
                kind=SchoolDomain.Kind.CUSTOM,
                verified_at=timezone.now(),
            )
        return school

    # --- G1: custom-domain routing suspended on deactivate -----------------
    def test_deactivate_suspends_custom_domain_routing(self):
        school = self._make_school("teardown-domain")
        apply_school_lifecycle_action(school, action="deactivate")

        school.refresh_from_db()
        self.assertFalse(school.is_active)
        self.assertFalse(school.custom_domain_verified, "white-label flag must clear")
        # Reversible: the domain string is RETAINED so reactivation can re-verify.
        self.assertEqual(school.custom_domain, "portal.example-school.edu")

        entry = SchoolDomain.objects.get(school=school, kind=SchoolDomain.Kind.CUSTOM)
        self.assertFalse(entry.is_verified, "custom domain must stop routing")
        self.assertIsNone(entry.verified_at)

    def test_subdomain_routing_is_not_touched(self):
        school = self._make_school("teardown-subdomain", with_custom_domain=False)
        sub = SchoolDomain.objects.create(
            school=school,
            domain="teardown-subdomain.runmycampus.com",
            is_verified=True,
            kind=SchoolDomain.Kind.SUBDOMAIN,
            verified_at=timezone.now(),
        )
        apply_school_lifecycle_action(school, action="deactivate")
        sub.refresh_from_db()
        self.assertTrue(sub.is_verified, "only CUSTOM domains are unbound, not subdomains")

    def test_unbind_is_idempotent(self):
        school = self._make_school("teardown-idem")
        first = unbind_custom_domains(school)
        self.assertEqual(first["suspended_domains"], ["portal.example-school.edu"])
        second = unbind_custom_domains(school)
        self.assertEqual(second["suspended_domains"], [], "second call is a no-op")

    # --- G2: billing subscription suspended on deactivate ------------------
    def test_deactivate_suspends_billing_subscription(self):
        school = self._make_school("teardown-billing", with_custom_domain=False)
        account, subscription, _ = ensure_subscription_for_school(school)
        subscription.status = TenantSubscription.Status.ACTIVE
        subscription.save(update_fields=["status", "updated_at"])
        account.status = BillingAccount.Status.ACTIVE
        account.save(update_fields=["status", "updated_at"])

        apply_school_lifecycle_action(school, action="deactivate")

        subscription.refresh_from_db()
        account.refresh_from_db()
        self.assertEqual(subscription.status, TenantSubscription.Status.SUSPENDED)
        self.assertEqual(account.status, BillingAccount.Status.SUSPENDED)

    def test_subscription_status_target_reflects_active_state(self):
        # Pure resume logic (no incident-sync interference): deactivation forces
        # SUSPENDED and reactivation recomputes back to ACTIVE.
        school = self._make_school("teardown-status", with_custom_domain=False)
        school.billing_type = school.BillingType.REGULAR
        school.is_frozen = False

        school.is_active = True
        self.assertEqual(
            _target_subscription_status_for_school(school),
            TenantSubscription.Status.ACTIVE,
        )
        school.is_active = False
        self.assertEqual(
            _target_subscription_status_for_school(school),
            TenantSubscription.Status.SUSPENDED,
        )
        school.is_active = True
        self.assertEqual(
            _target_subscription_status_for_school(school),
            TenantSubscription.Status.ACTIVE,
        )

    def test_activate_round_trips_is_active(self):
        school = self._make_school("teardown-resume", with_custom_domain=False)
        ensure_subscription_for_school(school)
        apply_school_lifecycle_action(school, action="deactivate")
        apply_school_lifecycle_action(school, action="activate")
        school.refresh_from_db()
        self.assertTrue(school.is_active)

    def test_lifecycle_result_reports_domain_unbind(self):
        school = self._make_school("teardown-report")
        result = apply_school_lifecycle_action(school, action="deactivate")
        self.assertIsNotNone(result["domain_unbind"])
        self.assertEqual(
            result["domain_unbind"]["suspended_domains"], ["portal.example-school.edu"]
        )
        # A non-deactivate action carries no domain teardown.
        result2 = apply_school_lifecycle_action(school, action="activate")
        self.assertIsNone(result2["domain_unbind"])
