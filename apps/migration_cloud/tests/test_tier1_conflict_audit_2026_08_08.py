"""Tier 1a A-Z upgrade wave (2026-08-08): field-level conflict-resolution
decisions enter the tamper-evident Migration Cloud audit chain.

The immutable chain already recorded operational events (companion / MAA / token
/ connector) and the coarse ``migration.bundle.applied``, but the actual
data-mutation DECISION — which fields of which tenant row an operator chose to
OVERWRITE / PRESERVE / MERGE during upsert-conflict review — left NO forensic
trail. ``MigrationCloudConflictsView.post`` now emits a ``migration.conflict
.resolved`` event (single resolve = field-level per-row; Fix-All = one batch
event carrying a capped per-row field summary), PII-free by construction: only
field NAMES + the resolution + the row identity land on the chain; the raw
before/after values stay in ``MigrationConflict`` (UI-masked per Tier-0).

Each test fails against the pre-Tier-1a code (no CONFLICT_RESOLVED event type,
no emission).
"""

from __future__ import annotations

import json
from unittest import mock

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.migration_cloud.models import (
    BundleStatus,
    ConflictResolution,
    IntakeMethod,
    MigrationBundle,
    MigrationConflict,
)
from apps.migration_cloud.models_audit import (
    MigrationCloudAuditEvent,
    MigrationCloudAuditEventType,
)
from apps.migration_cloud.views import MigrationCloudConflictsView
from apps.schools.models import School

_CONFLICT_RESOLVED = MigrationCloudAuditEventType.CONFLICT_RESOLVED.value


def _school(slug: str) -> School:
    return School.objects.create(name=slug, slug=slug, subdomain=slug, is_active=True)


def _bundle(school: School, key: str, status: str = BundleStatus.APPLIED) -> MigrationBundle:
    return MigrationBundle.objects.create(
        label=key,
        intake_method=IntakeMethod.FILE_UPLOAD,
        idempotency_key=key,
        status=status,
        school=school,
    )


def _conflict(bundle, pk_str, *, existing=None, incoming=None, changed=None) -> MigrationConflict:
    return MigrationConflict.objects.create(
        bundle=bundle,
        domain="students",
        canonical_model="apps.people.StudentProfile",
        canonical_pk=pk_str,
        existing_values=existing or {},
        incoming_values=incoming or {},
        changed_fields=changed or [],
    )


class _Base(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.school = _school("t1-a")
        self.user = User.objects.create_user(username="t1_user", password="x")
        self.bundle = _bundle(self.school, "t1-bundle")

    def _post(self, body, shell="portal", school=None):
        request = self.rf.post(
            f"/migration/{self.bundle.pk}/conflicts/",
            data=json.dumps(body),
            content_type="application/json",
        )
        request.user = self.user
        request.school = school if school is not None else self.school
        return MigrationCloudConflictsView.as_view()(
            request, bundle_id=self.bundle.pk, shell=shell
        )

    def _events(self):
        return list(
            MigrationCloudAuditEvent.objects.filter(event_type=_CONFLICT_RESOLVED)
        )


class ConflictAuditRegistrationTests(TestCase):
    def test_event_type_is_registered(self):
        self.assertIn(
            _CONFLICT_RESOLVED, {c.value for c in MigrationCloudAuditEventType}
        )
        self.assertEqual(_CONFLICT_RESOLVED, "migration.conflict.resolved")


class SingleResolveAuditTests(_Base):
    def test_single_resolve_writes_field_level_event(self):
        c = _conflict(self.bundle, "1", changed=["email", "phone"])
        resp = self._post({"conflict_id": c.pk, "resolution": "OVERWRITE"})
        self.assertEqual(resp.status_code, 200)
        events = self._events()
        self.assertEqual(len(events), 1)
        payload = events[0].payload_summary
        self.assertEqual(payload["resolution"], "OVERWRITE")
        self.assertEqual(payload["canonical_model"], "apps.people.StudentProfile")
        self.assertEqual(payload["canonical_pk"], "1")
        self.assertEqual(payload["changed_fields"], ["email", "phone"])
        self.assertEqual(payload["field_count"], 2)
        self.assertEqual(payload["bundle_id"], self.bundle.pk)

    def test_event_is_hash_chained_and_typed(self):
        c = _conflict(self.bundle, "1", changed=["dob"])
        self._post({"conflict_id": c.pk, "resolution": "PRESERVE"})
        ev = self._events()[0]
        self.assertEqual(ev.event_type, _CONFLICT_RESOLVED)
        self.assertTrue(ev.integrity_hash)
        self.assertEqual(len(ev.integrity_hash), 64)
        self.assertTrue(ev.prev_event_hash)  # genesis or a prior event hash
        # The tenant hash is derived from the school slug, never the raw slug.
        self.assertNotIn(self.school.slug, ev.tenant_id_hash)
        self.assertTrue(ev.event_subject_hash)  # row identity is hashed, not raw

    def test_no_raw_pii_on_the_chain(self):
        # The conflict holds a real SSN in existing_values; the audit event must
        # record only the CHANGED FIELD NAME ("ssn"), never the value.
        c = _conflict(
            self.bundle,
            "1",
            existing={"ssn": "123-45-6789", "first_name": "Ada"},
            incoming={"ssn": "987-65-4321"},
            changed=["ssn"],
        )
        self._post({"conflict_id": c.pk, "resolution": "OVERWRITE"})
        dumped = json.dumps(self._events()[0].payload_summary)
        self.assertNotIn("123-45-6789", dumped)
        self.assertNotIn("987-65-4321", dumped)
        self.assertIn("ssn", self._events()[0].payload_summary["changed_fields"])

    def test_invalid_resolution_writes_no_event(self):
        c = _conflict(self.bundle, "1", changed=["email"])
        resp = self._post({"conflict_id": c.pk, "resolution": "NOPE"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._events(), [])
        c.refresh_from_db()
        self.assertEqual(c.resolution, ConflictResolution.PENDING)


class FixAllAuditTests(_Base):
    def test_fix_all_writes_one_batch_event_with_field_rows(self):
        _conflict(self.bundle, "1", changed=["email"])
        _conflict(self.bundle, "2", changed=["phone", "grade"])
        _conflict(self.bundle, "3", changed=[])
        resp = self._post({"action": "fix_all", "resolution": "MERGE"})
        self.assertEqual(resp.status_code, 200)
        events = self._events()
        self.assertEqual(len(events), 1)
        payload = events[0].payload_summary
        self.assertEqual(payload["action"], "fix_all")
        self.assertEqual(payload["resolution"], "MERGE")
        self.assertEqual(payload["resolved_count"], 3)
        self.assertFalse(payload["rows_truncated"])
        self.assertEqual(len(payload["rows"]), 3)
        fields_by_pk = {r["pk"]: r["fields"] for r in payload["rows"]}
        self.assertEqual(fields_by_pk["2"], ["phone", "grade"])

    def test_fix_all_batch_event_has_no_raw_pii(self):
        _conflict(
            self.bundle,
            "1",
            existing={"national_id": "AAA0001112223"},
            changed=["national_id"],
        )
        self._post({"action": "fix_all", "resolution": "OVERWRITE"})
        dumped = json.dumps(self._events()[0].payload_summary)
        self.assertNotIn("AAA0001112223", dumped)
        self.assertIn("national_id", dumped)  # field name is fine

    def test_fix_all_flags_truncation_over_cap(self):
        # 3 pending rows, cap patched to 2 → count exact (3), rows capped at 2,
        # truncation flagged (the "no silent caps" contract).
        for i in range(3):
            _conflict(self.bundle, str(i), changed=["email"])
        with mock.patch("apps.migration_cloud.views._MC_AUDIT_ROW_CAP", 2):
            resp = self._post({"action": "fix_all", "resolution": "PRESERVE"})
        self.assertEqual(resp.status_code, 200)
        payload = self._events()[0].payload_summary
        self.assertEqual(payload["resolved_count"], 3)
        self.assertEqual(len(payload["rows"]), 2)
        self.assertTrue(payload["rows_truncated"])


class AuditBestEffortTests(_Base):
    def test_audit_failure_never_breaks_resolution(self):
        c = _conflict(self.bundle, "1", changed=["email"])
        with mock.patch.object(
            MigrationCloudAuditEvent.objects, "record", side_effect=RuntimeError("boom")
        ):
            resp = self._post({"conflict_id": c.pk, "resolution": "OVERWRITE"})
        # Resolution still succeeds; the audit write is best-effort.
        self.assertEqual(resp.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.resolution, ConflictResolution.OVERWRITE)
        self.assertEqual(self._events(), [])
