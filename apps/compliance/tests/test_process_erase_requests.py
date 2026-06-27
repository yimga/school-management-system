"""Wave G: process_erase_requests management command tests.

Verifies the batch runner correctly mutates EraseRequest state and
gracefully handles the no-StudentProfile path. The actual scrubbing is
unit-tested elsewhere in `apps.compliance.tests`; here we just exercise
the wiring.
"""

from __future__ import annotations

import uuid
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.compliance.models import EraseRequest
from apps.schools.models import School
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig

User = get_user_model()


def _make_school(plan, region):
    slug = f"er-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=slug, slug=slug, subdomain=slug, is_active=True,
        plan=plan, default_region=region, settings={},
    )


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class ProcessEraseRequestsTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="ER", slug="er", included_features=["core"], is_active=True)
        cls.region = RegionConfig.objects.create(code="ER", name="ERland", timezone="UTC", default_currency="USD")

    def setUp(self):
        EraseRequest.objects.all().delete()
        self.school = _make_school(self.plan, self.region)
        self.subject = User.objects.create_user(username=f"sub-{uuid.uuid4().hex[:6]}", password="pw")

    def _approved_request(self):
        return EraseRequest.objects.create(
            school=self.school,
            subject_user=self.subject,
            status=EraseRequest.Status.APPROVED,
        )

    def test_no_subject_relationship_skipped_as_failure(self):
        # A subject User with no student/staff/guardian relationship in the
        # tenant resolves to unsupported_subject_kind and is not completed.
        req = self._approved_request()
        out = StringIO()
        call_command("process_erase_requests", "--dry-run", stdout=out)
        body = out.getvalue()
        self.assertIn(f"req#{req.pk}", body)
        self.assertIn("FAIL", body)
        req.refresh_from_db()
        self.assertEqual(req.status, EraseRequest.Status.APPROVED)  # untouched

    def test_dry_run_does_not_mutate(self):
        req = self._approved_request()
        with mock.patch(
            "apps.compliance.management.commands.process_erase_requests.scrub_user_subject",
            return_value={"ok": True, "scrubbed": 1},
        ):
            out = StringIO()
            call_command("process_erase_requests", "--dry-run", stdout=out)
        req.refresh_from_db()
        self.assertEqual(req.status, EraseRequest.Status.APPROVED)
        self.assertIsNone(req.completed_at)

    def test_live_run_marks_completed(self):
        req = self._approved_request()
        with mock.patch(
            "apps.compliance.management.commands.process_erase_requests.scrub_user_subject",
            return_value={"ok": True, "scrubbed": 1},
        ):
            out = StringIO()
            call_command("process_erase_requests", stdout=out)
        req.refresh_from_db()
        self.assertEqual(req.status, EraseRequest.Status.COMPLETED)
        self.assertIsNotNone(req.completed_at)

    def test_failed_scrub_keeps_status_approved(self):
        req = self._approved_request()
        with mock.patch(
            "apps.compliance.management.commands.process_erase_requests.scrub_user_subject",
            return_value={"ok": False, "error": "boom"},
        ):
            out = StringIO()
            call_command("process_erase_requests", stdout=out)
        req.refresh_from_db()
        self.assertEqual(req.status, EraseRequest.Status.APPROVED)
        self.assertIn("FAIL", out.getvalue())

    def test_school_filter(self):
        req_in = self._approved_request()
        other_school = _make_school(self.plan, self.region)
        other_subject = User.objects.create_user(username=f"o-{uuid.uuid4().hex[:6]}", password="pw")
        req_out = EraseRequest.objects.create(
            school=other_school, subject_user=other_subject,
            status=EraseRequest.Status.APPROVED,
        )
        with mock.patch(
            "apps.compliance.management.commands.process_erase_requests.scrub_user_subject",
            return_value={"ok": True, "scrubbed": 1},
        ):
            out = StringIO()
            call_command("process_erase_requests", "--school", self.school.slug, stdout=out)
        req_in.refresh_from_db()
        req_out.refresh_from_db()
        self.assertEqual(req_in.status, EraseRequest.Status.COMPLETED)
        self.assertEqual(req_out.status, EraseRequest.Status.APPROVED)  # other tenant untouched
