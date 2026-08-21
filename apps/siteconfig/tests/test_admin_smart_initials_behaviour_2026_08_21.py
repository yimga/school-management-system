"""Behavioural proof for admin auto-fill, written against the PRE-EXISTING API only.

Its sibling ``test_admin_smart_initials_2026_08_21`` imports the new resolver
symbols, so against the pre-expansion module that file does not collect at all —
and a test that never collected has not run.  This file imports nothing that did
not already exist, so on the old implementation it collects cleanly and fails as
ordinary assertions: ``build_admin_smart_initials`` returned ``{}`` for every model
except ``academics.academicyear``.

That distinction is the point.  These are the assertions that would catch a silent
revert of the resolver layer while leaving the module importable.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear, Term
from apps.schools.models import School
from apps.siteconfig.admin_smart_initials import build_admin_smart_initials
from apps.siteconfig.models_platform_catalog import RegionConfig


class SmartInitialsBehaviourTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="smart-initials-behaviour",
            email="smart-initials-behaviour@example.test",
            password="test-only-password",
        )
        cls.region = RegionConfig.objects.create(
            code="rmc-behaviour-region", name="Behaviour Region"
        )
        cls.school = School.objects.create(
            name="Behaviour School",
            slug="smart-behaviour",
            subdomain="smart-behaviour",
            country_code="CM",
            currency="XAF",
            default_region=cls.region,
            is_active=True,
        )
        today = timezone.now().date()
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="Behaviour 2026/2027",
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=300),
            is_active=True,
        )
        cls.term = Term.objects.create(
            school=cls.school,
            academic_year=cls.year,
            name="FIRST",
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=60),
            is_active=True,
        )

    def _request(self):
        request = RequestFactory().get(
            "/admin/", HTTP_HOST="smart-behaviour.runmycampus.com"
        )
        request.user = self.user
        request.school = self.school
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        SessionMiddleware(lambda _r: None).process_request(request)
        MessageMiddleware(lambda _r: None).process_request(request)
        return request

    def test_a_model_with_no_exact_builder_still_receives_suggestions(self):
        """The whole expansion in one assertion: coverage beyond the registry."""
        from apps.siteconfig.admin_smart_initials import INITIAL_BUILDERS

        self.assertNotIn(
            Term._meta.label_lower,
            INITIAL_BUILDERS,
            "fixture assumption broken: academics.term now has an exact builder",
        )
        values = build_admin_smart_initials(Term, self._request())
        self.assertEqual(
            values.get("academic_year"),
            self.year.pk,
            "academics.term has no exact builder, so this value can only come "
            "from the generic field-resolver layer",
        )

    def test_region_is_suggested_from_the_schools_configuration(self):
        from apps.global_registries.models import HolidayCalendar

        values = build_admin_smart_initials(HolidayCalendar, self._request())
        self.assertEqual(values.get("region"), self.region.pk)

    def test_actor_field_is_suggested_as_the_signed_in_user(self):
        from apps.analytics.models import GradePredictionLabel

        values = build_admin_smart_initials(GradePredictionLabel, self._request())
        self.assertEqual(values.get("labeled_by"), self.user.pk)

    def test_coverage_spans_many_models_not_one(self):
        """Guards the specific regression of collapsing back to a single builder."""
        from config.admin import tenant_admin_site

        request = self._request()
        covered = 0
        for model in tenant_admin_site._registry:
            try:
                if build_admin_smart_initials(model, request):
                    covered += 1
            except Exception:  # noqa: BLE001 - counted by the sibling suite
                continue
        self.assertGreaterEqual(
            covered,
            25,
            f"only {covered} tenant models received any suggestion; the generic "
            "resolver layer is not reaching the registry",
        )
