"""HTTP tests for guided onboarding CSV dry-run and apply (batch 1516)."""

from __future__ import annotations

import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.customersuccess.views_tenant import (
    guided_onboarding_csv_apply,
    guided_onboarding_csv_dry_run,
)
from apps.people.models import StudentProfile
from apps.schools.models import School

_GOOD_CSV = (
    "external_id,first_name,last_name\n"
    "HTTP-1,Ada,Lovelace\n"
)


@override_settings(ALLOWED_HOSTS=["*"])
class GuidedOnboardingCSVViewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="CSV School",
            slug="csv-school",
            subdomain="csv-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="csv_admin",
            password="Test1234!",
            is_staff=True,
            role=User.Role.ADMIN,
        )
        self.factory = RequestFactory()

    def _upload(self, text: str = _GOOD_CSV) -> SimpleUploadedFile:
        return SimpleUploadedFile("roster.csv", text.encode("utf-8"), content_type="text/csv")

    def test_dry_run_returns_validation_payload(self):
        req = self.factory.post(
            reverse("siteconfig:guided_onboarding_csv_dry_run"),
            data={"csv_file": self._upload()},
        )
        req.user = self.user
        req.school = self.school
        resp = guided_onboarding_csv_dry_run(req)
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content)
        self.assertTrue(payload.get("ok"))
        self.assertTrue(payload.get("is_valid"))
        self.assertEqual(len(payload.get("rows", [])), 1)

    def test_apply_creates_student(self):
        req = self.factory.post(
            reverse("siteconfig:guided_onboarding_csv_apply"),
            data={"csv_file": self._upload()},
        )
        req.user = self.user
        req.school = self.school
        resp = guided_onboarding_csv_apply(req)
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content)
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload.get("created"), 1)
        self.assertTrue(
            StudentProfile.objects.filter(school=self.school, is_active=True).exists()
        )

    def test_non_staff_forbidden(self):
        parent = User.objects.create_user(
            username="csv_parent",
            password="Test1234!",
            role=User.Role.PARENT,
        )
        req = self.factory.post(
            reverse("siteconfig:guided_onboarding_csv_dry_run"),
            data={"csv_file": self._upload()},
        )
        req.user = parent
        req.school = self.school
        resp = guided_onboarding_csv_dry_run(req)
        self.assertEqual(resp.status_code, 403)
