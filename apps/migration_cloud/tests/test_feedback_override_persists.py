"""T15 regression: an operator OVERRIDE on the mapping editor must rewrite the
current bundle's ``mapping_summary`` — not just record next-bundle recall.

Before the fix, ``MigrationCloudFeedbackView`` recorded feedback + the
AIEmbeddingStore recall decision, but never touched ``bundle.mapping_summary``.
So the drag-and-drop / "Override" UI showed a "saved" toast while ``apply``
silently used the ORIGINAL AI mapping — the operator migrated with the wrong
mapping without any signal. These tests lock the corrected behaviour:

    * A manual correction (manual_correction=True) with a NEW canonical field
      rewrites the matching row in ``mapping_summary["per_artifact"]``.
    * A plain accept (accepted=True, manual_correction=False) leaves the
      mapping untouched — nothing changed, so nothing to rewrite.
    * An override on an already-APPLIED bundle still rewrites AND flags
      ``reapply_required`` so the UI can tell the operator to re-run Apply.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle


def _operator():
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="ops-feedback@example.com",
        defaults={
            "email": "ops-feedback@example.com",
            "is_staff": True,
            "is_superuser": True,
        },
    )
    user.set_password("x")
    user.save()
    return user


class FeedbackOverridePersistsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)
        self.bundle = MigrationBundle.objects.create(
            label="feedback override test",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="feedback-override-test",
            status=BundleStatus.MAPPED,
            mapping_summary={
                "per_artifact": {
                    "students.csv": [
                        {
                            "source_column": "Student_Number",
                            "canonical_field": "custom_fields.student_number",
                            "confidence": 0.55,
                            "method": "ai_bridge",
                        },
                        {
                            "source_column": "Email",
                            "canonical_field": "student.email",
                            "confidence": 0.97,
                            "method": "heuristic",
                        },
                    ]
                }
            },
        )
        self.url = reverse(
            "migration_cloud_super:bundle_feedback", kwargs={"bundle_id": self.bundle.pk}
        )

    def _override(self, source_column, canonical_field):
        return self.client.post(
            self.url,
            data=json.dumps(
                {
                    "accepted": False,
                    "manual_correction": True,
                    "prompt_type": "migration_cloud.field_mapper",
                    "answer": canonical_field,
                    "mapping": {
                        "source_column": source_column,
                        "canonical_field": canonical_field,
                        "domain": "students",
                        "transformer": None,
                        "sample_values": [],
                    },
                }
            ),
            content_type="application/json",
        )

    def test_override_rewrites_current_bundle_mapping(self):
        resp = self._override("Student_Number", "student.external_id")
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data["recorded"])
        self.assertTrue(data["applied_to_bundle"])
        self.assertIn("students.csv", data["artifacts_updated"])
        self.assertFalse(data["reapply_required"])  # bundle still MAPPED

        self.bundle.refresh_from_db()
        mappings = self.bundle.mapping_summary["per_artifact"]["students.csv"]
        target = next(m for m in mappings if m["source_column"] == "Student_Number")
        self.assertEqual(target["canonical_field"], "student.external_id")
        self.assertEqual(target["method"], "operator_override")
        self.assertGreaterEqual(target["confidence"], 0.95)
        # The untouched row is preserved verbatim.
        other = next(m for m in mappings if m["source_column"] == "Email")
        self.assertEqual(other["canonical_field"], "student.email")

    def test_plain_accept_does_not_rewrite_mapping(self):
        resp = self.client.post(
            self.url,
            data=json.dumps(
                {
                    "accepted": True,
                    "manual_correction": False,
                    "prompt_type": "migration_cloud.field_mapper",
                    "answer": "custom_fields.student_number",
                    "mapping": {
                        "source_column": "Student_Number",
                        "canonical_field": "custom_fields.student_number",
                        "domain": "students",
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertFalse(data["applied_to_bundle"])
        self.assertEqual(data["artifacts_updated"], [])
        self.bundle.refresh_from_db()
        target = next(
            m
            for m in self.bundle.mapping_summary["per_artifact"]["students.csv"]
            if m["source_column"] == "Student_Number"
        )
        # Unchanged — an accept means "the AI mapping is fine".
        self.assertEqual(target["canonical_field"], "custom_fields.student_number")
        self.assertEqual(target["method"], "ai_bridge")

    def test_override_on_applied_bundle_flags_reapply(self):
        self.bundle.status = BundleStatus.APPLIED
        self.bundle.save(update_fields=["status"])
        resp = self._override("Student_Number", "student.external_id")
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data["applied_to_bundle"])
        self.assertTrue(data["reapply_required"])

    def test_override_to_same_value_is_noop(self):
        # Overriding to the value already stored changes nothing.
        resp = self._override("Email", "student.email")
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertFalse(data["applied_to_bundle"])
        self.assertEqual(data["artifacts_updated"], [])
