"""SFDP 1422 — provision binds TenantPaymentPolicy from school country."""

from __future__ import annotations

from django.test import TestCase

from apps.finance.models import TenantPaymentPolicy
from apps.finance.payment_provision import bind_tenant_payment_policy_for_school
from apps.finance.payment_region_catalog import ensure_canonical_region_payment_profiles
from apps.schools.models import School


class PaymentProvisionBindTests(TestCase):
    def setUp(self):
        ensure_canonical_region_payment_profiles()

    def test_ng_school_gets_paystack_primary_rail(self):
        school = School.objects.create(
            name="Lagos Academy",
            slug="lagos-academy-bind",
            subdomain="lagos-academy-bind",
            country_code="NG",
            is_active=True,
        )
        result = bind_tenant_payment_policy_for_school(school)
        self.assertTrue(result["bound"])
        self.assertEqual(result["iso2"], "NG")
        self.assertEqual(result["primary_rail"], "ng-paystack")
        policy = TenantPaymentPolicy.objects.get(school=school)
        self.assertEqual(policy.region_profile.country_code, "NG")

    def test_cm_school_gets_mtn_primary(self):
        school = School.objects.create(
            name="Douala School",
            slug="douala-bind",
            subdomain="douala-bind",
            country_code="CM",
            is_active=True,
        )
        result = bind_tenant_payment_policy_for_school(school)
        self.assertTrue(result["bound"])
        self.assertEqual(result["primary_rail"], "cm-mtn")

    def test_gh_school_gets_mtn_primary(self):
        school = School.objects.create(
            name="Accra School",
            slug="accra-bind",
            subdomain="accra-bind",
            country_code="GH",
            is_active=True,
        )
        result = bind_tenant_payment_policy_for_school(school)
        self.assertTrue(result["bound"])
        self.assertEqual(result["primary_rail"], "gh-mtn")
