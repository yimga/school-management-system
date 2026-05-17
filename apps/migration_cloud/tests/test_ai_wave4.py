"""Tests for the wave 4 AI surface: conversational rebind, bundle Q&A,
reconciliation narrative, vendor-from-image.

AI is disabled in the test environment, so the assertions focus on:
    * Deterministic regex path of `parse_mapping_command` (must work
      without AI — this is the operator's lifeline).
    * View behaviour when AI is unavailable (clean 422 / ai_available=False,
      never an opaque 500).
    * Mapping edit actually lands in `bundle.mapping_summary`.
    * Reconciliation narrative endpoint returns 409 when no report exists.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from apps.migration_cloud.ai_bridge import parse_mapping_command
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle


def _operator():
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="ops-w4@example.com",
        defaults={"email": "ops-w4@example.com", "is_staff": True, "is_superuser": True},
    )
    user.set_password("x")
    user.save()
    return user


class CommandHeuristicTests(TestCase):
    """parse_mapping_command must work WITHOUT AI for the common phrasings."""

    def test_set_as(self):
        proposal = parse_mapping_command(
            school=None,
            command="set Student_Number as student.external_id",
            available_source_columns=["Student_Number", "Email"],
            available_canonical_fields=["student.external_id", "student.email"],
        )
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.answer["source_column"], "Student_Number")
        self.assertEqual(proposal.answer["canonical_field"], "student.external_id")
        self.assertEqual(proposal.provider_meta["method"], "regex")

    def test_map_to(self):
        proposal = parse_mapping_command(
            school=None,
            command="map Homeroom to custom_fields.homeroom",
            available_source_columns=["Homeroom"],
            available_canonical_fields=["custom_fields.homeroom"],
        )
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.answer["source_column"], "Homeroom")

    def test_arrow_form(self):
        proposal = parse_mapping_command(
            school=None,
            command="Birth_Date -> student.date_of_birth",
            available_source_columns=["Birth_Date"],
            available_canonical_fields=["student.date_of_birth"],
        )
        self.assertIsNotNone(proposal)

    def test_unknown_phrasing_no_ai_returns_none(self):
        proposal = parse_mapping_command(
            school=None,
            command="please change the student number column somehow",
            available_source_columns=["Student_Number"],
            available_canonical_fields=["student.external_id"],
        )
        # No AI available + heuristic does not match the freeform phrasing → None.
        self.assertIsNone(proposal)


class AIRebindViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)
        self.bundle = MigrationBundle.objects.create(
            label="rebind test",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="rebind-test",
            status=BundleStatus.MAPPED,
            mapping_summary={
                "per_artifact": {
                    "students.csv": [
                        {"source_column": "Student_Number", "canonical_field": "custom_fields.student_number",
                         "confidence": 0.55, "method": "ai_bridge"},
                        {"source_column": "Email", "canonical_field": "student.email",
                         "confidence": 0.97, "method": "heuristic"},
                    ]
                }
            },
        )
        self.url = reverse(
            "migration_cloud_super:bundle_ai_rebind", kwargs={"bundle_id": self.bundle.pk}
        )

    def test_regex_rebind_applies_and_updates_mapping_summary(self):
        resp = self.client.post(self.url, data=json.dumps({
            "command": "set Student_Number as student.external_id"
        }), content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data["applied"])
        self.bundle.refresh_from_db()
        mappings = self.bundle.mapping_summary["per_artifact"]["students.csv"]
        target = next(m for m in mappings if m["source_column"] == "Student_Number")
        self.assertEqual(target["canonical_field"], "student.external_id")
        self.assertEqual(target["method"], "operator_command")
        self.assertGreaterEqual(target["confidence"], 0.95)

    def test_unknown_column_returns_404(self):
        resp = self.client.post(self.url, data=json.dumps({
            "command": "set Nonexistent_Column as student.email"
        }), content_type="application/json")
        self.assertEqual(resp.status_code, 404)

    def test_empty_command_400(self):
        resp = self.client.post(self.url, data=json.dumps({"command": ""}),
                                 content_type="application/json")
        self.assertEqual(resp.status_code, 400)


class AIAskViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)
        self.bundle = MigrationBundle.objects.create(
            label="ask test",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="ask-test",
            status=BundleStatus.MAPPED,
        )

    def test_question_without_ai_returns_clean_payload(self):
        url = reverse("migration_cloud_super:bundle_ai_ask",
                      kwargs={"bundle_id": self.bundle.pk})
        resp = self.client.post(url, data=json.dumps({
            "question": "How many artifacts are in this bundle?"
        }), content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # AI not available in tests → ai_available=False, answer=None, no crash.
        self.assertFalse(data["ai_available"])
        self.assertIsNone(data["answer"])

    def test_long_question_400(self):
        url = reverse("migration_cloud_super:bundle_ai_ask",
                      kwargs={"bundle_id": self.bundle.pk})
        resp = self.client.post(url, data=json.dumps({"question": "x" * 600}),
                                 content_type="application/json")
        self.assertEqual(resp.status_code, 400)


class AIReconcileNarrativeViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)

    def test_no_report_returns_409(self):
        bundle = MigrationBundle.objects.create(
            label="rec test", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="rec-test", status=BundleStatus.MAPPED,
        )
        url = reverse("migration_cloud_super:bundle_ai_narrate_reconciliation",
                      kwargs={"bundle_id": bundle.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 409)

    def test_with_report_returns_200_even_without_ai(self):
        bundle = MigrationBundle.objects.create(
            label="rec test 2", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="rec-test-2", status=BundleStatus.RECONCILED,
            reconciliation_summary={"overall_parity_pct": 99.2, "per_domain": [], "notes": []},
        )
        url = reverse("migration_cloud_super:bundle_ai_narrate_reconciliation",
                      kwargs={"bundle_id": bundle.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["overall_parity_pct"], 99.2)
        self.assertFalse(data["ai_available"])  # AI off in tests


class AIVendorFromImageViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("migration_cloud_super:ai_vendor_from_image")

    def test_missing_image_400(self):
        resp = self.client.post(self.url, data={})
        self.assertEqual(resp.status_code, 400)

    def test_unsupported_suffix_415(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("doc.txt", b"not an image",
                                     content_type="text/plain")
        resp = self.client.post(self.url, data={"image": upload})
        self.assertEqual(resp.status_code, 415)
