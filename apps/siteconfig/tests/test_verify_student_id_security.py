import base64
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.siteconfig.student_id_service import create_student_verify_token


@override_settings(SECRET_KEY="student-id-test-secret")
class VerifyStudentIdSecurityTests(TestCase):
    def test_forged_student_id_token_is_rejected(self):
        token = create_student_verify_token(
            school_id="school-a",
            student_id="student-a",
            student_name="Ada Student",
            grade="Form 1",
        )
        header, payload, signature = token.split(".")
        decoded = json.loads(base64.urlsafe_b64decode(payload + "==").decode())
        decoded["student_id"] = "student-b"
        forged_payload = (
            base64.urlsafe_b64encode(json.dumps(decoded).encode())
            .rstrip(b"=")
            .decode("ascii")
        )
        forged = f"{header}.{forged_payload}.{signature}"

        response = self.client.get(
            reverse("verify_student_id", kwargs={"token": forged}),
            REMOTE_ADDR="198.51.100.10",
        )

        self.assertEqual(response.status_code, 401)

    def test_verify_student_id_response_exposes_public_fields_only(self):
        token = create_student_verify_token(
            school_id="school-a",
            student_id="student-a",
            student_name="Ada Student",
            photo_url="https://cdn.example.test/ada.jpg",
            grade="Form 1",
        )

        response = self.client.get(
            reverse("verify_student_id", kwargs={"token": token}),
            REMOTE_ADDR="198.51.100.11",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload.keys()),
            {"name", "photo", "status", "grade"},
        )
        self.assertNotIn("school_id", payload)
        self.assertNotIn("student_id", payload)
