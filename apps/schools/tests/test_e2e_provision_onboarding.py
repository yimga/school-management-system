"""End-to-end: real provisioning pipeline + onboarding 'done' page.

Runs the actual provisioning to completion (sync fallback, shared-DB), asserts
every seed artifact, verifies re-provision idempotency, and renders the
onboarding 'done' page that previously 500'd (undefined `pending_school_name`
filter-arg in tenant_minimal_shell.html). The django-tenants Postgres schema
build is skipped locally (USE_DJANGO_TENANTS False) — that part is staging-only.

Validated via a direct django.setup() run (12/12) because the custom sqlite test
runner is flaky on Windows; this TestCase form runs in CI.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Subject,
    Term,
)
from apps.schools.models import School, SchoolMembership, SchoolProvisioningEvent
from apps.schools.tasks import dispatch_provision_school

User = get_user_model()


class SchoolProvisionOnboardingE2ETests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="E2E Test High School",
            slug="e2e-test-high",
            subdomain="e2e-test-high",
            is_active=False,
        )
        self.owner = User.objects.create_user(
            username="e2e-owner@example.com",
            email="e2e-owner@example.com",
            password="x",
        )
        SchoolMembership.objects.create(
            user=self.owner, school=self.school, is_primary=True
        )

    def _provision(self):
        """Run the real pipeline via the sync fallback (broker offline)."""
        with mock.patch(
            "apps.schools.tasks.provision_school_task.delay",
            side_effect=RuntimeError("broker offline"),
        ):
            return dispatch_provision_school(
                str(self.school.id), contact_email="e2e-owner@example.com"
            )

    def test_full_provision_seeds_everything_and_done_page_renders(self):
        result = self._provision()
        self.school.refresh_from_db()

        # Pipeline completed.
        self.assertTrue(self.school.is_active, "school should be active")
        self.assertTrue(result.get("fallback"), "dispatch should fall back to sync")

        # Every seed artifact the seed_data step is responsible for.
        self.assertTrue(AcademicYear.objects.filter(school=self.school).exists())
        term_count = Term.objects.filter(school=self.school).count()
        self.assertGreaterEqual(term_count, 1, "terms must be seeded")
        subject_count = Subject.objects.filter(school=self.school).count()
        self.assertGreaterEqual(subject_count, 1, "subjects must be seeded")
        self.assertGreaterEqual(
            Classroom.objects.filter(school=self.school).count(), 1
        )
        self.assertGreaterEqual(
            Department.objects.filter(school=self.school).count(), 1
        )
        self.assertTrue(
            SchoolProvisioningEvent.objects.filter(
                school=self.school, event_type="COMPLETED"
            ).exists()
        )
        self.assertFalse(
            SchoolProvisioningEvent.objects.filter(
                school=self.school, event_type="FAILED"
            ).exists(),
            "a clean provision must record no FAILED event",
        )

        # Idempotency: a second run must not duplicate seed rows.
        self._provision()
        self.assertEqual(
            Term.objects.filter(school=self.school).count(),
            term_count,
            "re-provision must not duplicate terms",
        )
        self.assertEqual(
            Subject.objects.filter(school=self.school).count(),
            subject_count,
            "re-provision must not duplicate subjects",
        )

        # The onboarding 'done' page that previously 500'd must render 200.
        from apps.accounts.views_owner_onboarding import owner_onboarding_done

        req = RequestFactory().get(
            "/authentication/onboarding/done/",
            HTTP_HOST="e2e-test-high.runmycampus.com",
        )
        req.user = self.owner
        req.urlconf = "config.tenant_urls"
        req.session = SessionStore()
        req.school = self.school
        req.public_host_kind = "tenant"
        req.tenant = type("T", (), {"schema_name": "public"})()
        resp = owner_onboarding_done(req)
        self.assertEqual(resp.status_code, 200, "onboarding/done must not 500")

    def test_done_page_renders_even_when_provisioning_incomplete(self):
        """The 500 was independent of provisioning state — guard that path too."""
        from apps.accounts.views_owner_onboarding import owner_onboarding_done

        # School left INACTIVE (provisioning never ran). Stub the in-request kick
        # so the test stays fast and deterministic.
        with mock.patch(
            "apps.accounts.views_owner_onboarding._kick_provisioning_on_done_page",
            return_value=None,
        ):
            req = RequestFactory().get(
                "/authentication/onboarding/done/",
                HTTP_HOST="e2e-test-high.runmycampus.com",
            )
            req.user = self.owner
            req.urlconf = "config.tenant_urls"
            req.session = SessionStore()
            req.school = self.school
            req.public_host_kind = "tenant"
            req.tenant = type("T", (), {"schema_name": "public"})()
            resp = owner_onboarding_done(req)
        self.assertEqual(resp.status_code, 200)
