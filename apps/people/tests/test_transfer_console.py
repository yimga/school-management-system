"""Transfer Wave B — operator console smoke (/portal/super/transfers/)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.people.models import StudentProfile
from apps.people.models_transfer import TransferCase
from apps.schools.models import School

User = get_user_model()


class TransferConsoleTests(TestCase):
    def setUp(self):
        self.source = School.objects.create(
            name="Console Src", slug="console-src", subdomain="console-src"
        )
        self.target = School.objects.create(
            name="Console Tgt", slug="console-tgt", subdomain="console-tgt"
        )
        self.profile = StudentProfile.objects.create(
            school=self.source,
            first_name="Con",
            last_name="Sole",
            student_code="CO-001",
        )
        self.staff = User.objects.create_user(
            username="console_staff",
            password="pass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.staff)

    def test_non_staff_redirected(self):
        self.client.logout()
        response = self.client.get(reverse("portal:transfer_cases_index"))
        self.assertEqual(response.status_code, 302)

    def test_create_then_request_consent_flow(self):
        response = self.client.post(
            reverse("portal:transfer_case_create"),
            {
                "student_pk": str(self.profile.pk),
                "target_school_id": str(self.target.pk),
                "format": "json",
            },
        )
        self.assertEqual(response.status_code, 201)
        case_id = response.json()["case"]["id"]

        response = self.client.post(
            reverse("portal:transfer_case_request_consent"),
            {
                "case_id": case_id,
                "guardian_name": "Guard Ian",
                "guardian_email": "guardian@example.com",
                "format": "json",
            },
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIn("token=", body["consent_url_path"])
        self.assertEqual(body["case"]["status"], TransferCase.Status.CONSENT_PENDING)

        # Index sees the case (JSON branch).
        response = self.client.get(
            reverse("portal:transfer_cases_index"), {"format": "json"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_create_rejects_same_school(self):
        response = self.client.post(
            reverse("portal:transfer_case_create"),
            {
                "student_pk": str(self.profile.pk),
                "target_school_id": str(self.source.pk),
                "format": "json",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_run_refuses_unapproved_case(self):
        case = TransferCase.objects.create(
            source_school=self.source,
            target_school=self.target,
            source_profile_pk=str(self.profile.pk),
        )
        response = self.client.post(
            reverse("portal:transfer_case_run"),
            {"case_id": str(case.pk), "format": "json"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["ok"])

    def test_html_index_renders(self):
        response = self.client.get(reverse("portal:transfer_cases_index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student transfers")
