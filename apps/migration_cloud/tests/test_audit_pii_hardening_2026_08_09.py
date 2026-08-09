"""Audit / PII hardening seals from the 2026-08-09 re-audit.

1. The audit sanitizer block-list (_SENSITIVE_KEYS) was narrower than
   pii_display's PII hints, and "dob" (a substring test) never matched
   "date_of_birth" -- so cleartext PII could ride into the append-only,
   exportable audit chain as a dict VALUE under an un-listed key.
2. The conflict-review view masked PENDING existing/incoming values for an
   unprivileged viewer but placed RESOLVED rows in the context UNMASKED.
"""

from __future__ import annotations

from unittest import mock

from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.migration_cloud.models import (
    BundleStatus,
    ConflictResolution,
    IntakeMethod,
    MigrationBundle,
    MigrationConflict,
)
from apps.migration_cloud.models_audit import _sanitize_payload
from apps.migration_cloud.views import MigrationCloudConflictsView
from apps.schools.models import School


class SanitizerBlockListTests(SimpleTestCase):
    def test_newly_blocked_pii_keys_raise(self):
        for key in (
            "date_of_birth", "guardian_phone", "national_id_number",
            "passport_no", "medical_notes", "health_conditions",
            "allergies", "mobile_number", "monthly_salary", "iban",
        ):
            with self.assertRaises(ValueError, msg=key):
                _sanitize_payload({key: "sensitive"})

    def test_benign_keys_still_pass(self):
        # Count / structural keys used by real emit sites must NOT be rejected.
        for payload in (
            {"created_count": 5, "updated_count": 2},
            {"incoming_values": {"a": 1}, "changed_fields": ["x"]},
            {"domains": {"students": {"created": 3}}},
            {"reason": "resolved", "via": "api"},
        ):
            self.assertEqual(_sanitize_payload(payload), payload)


class ConflictResolvedMaskingTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school = School.objects.create(
            name="Mask", slug="mask-seal", subdomain="mask-seal",
            is_active=True, country_code="CM",
        )
        self.bundle = MigrationBundle.objects.create(
            label="mask", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="mask-1", status=BundleStatus.MAPPED, school=self.school,
        )
        # A RESOLVED conflict carrying raw PII in its existing/incoming values.
        MigrationConflict.objects.create(
            bundle=self.bundle, domain="students",
            canonical_model="apps.people.models.StudentProfile", canonical_pk="1",
            legacy_id="PS-1",
            existing_values={"date_of_birth": "2010-01-01", "ssn": "123-45-6789"},
            incoming_values={"date_of_birth": "2011-02-02"},
            changed_fields=["date_of_birth"],
            resolution=ConflictResolution.OVERWRITE, resolved_at=timezone.now(),
        )
        # A non-superuser has no reveal-PII right.
        self.user = User.objects.create_user(username="mask_viewer", password="x")

    def test_resolved_values_masked_for_unprivileged_viewer(self):
        request = self.rf.get("/super/migration/conflicts/")
        request.user = self.user
        captured = {}

        def _fake_render(req, template, context, *a, **k):
            captured["resolved"] = list(context.get("resolved", []))
            from django.http import HttpResponse

            return HttpResponse(b"ok")

        with mock.patch(
            "apps.migration_cloud.views._tenant_scoped_bundle",
            return_value=self.bundle,
        ), mock.patch("apps.migration_cloud.views.render", _fake_render):
            MigrationCloudConflictsView.as_view()(
                request, bundle_id=self.bundle.pk, shell="super",
            )

        self.assertTrue(captured["resolved"])
        existing = captured["resolved"][0].existing_values
        # The raw DOB / SSN must NOT survive into the response context.
        self.assertNotEqual(existing.get("date_of_birth"), "2010-01-01")
        self.assertNotEqual(existing.get("ssn"), "123-45-6789")
