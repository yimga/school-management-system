"""Wave E — platform-wide signed non-repudiation action log."""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.compliance.models import (
    NonRepudiationLogEntry,
    NonRepudiationLogReadOnlyError,
)
from apps.compliance.non_repudiation import record_action, verify_chain
from apps.schools.models import School


class NonRepudiationTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"NR {uid}", slug=f"nr-{uid}", subdomain=f"nr{uid}", is_active=True
        )

    def test_records_chain_with_genesis(self):
        e0 = record_action(action="config.update", resource="brand", school_id=self.school.id)
        self.assertEqual(e0.sequence, 0)
        self.assertEqual(e0.prev_hash, "genesis")
        e1 = record_action(action="billing.refund", resource="inv:5", school_id=self.school.id)
        self.assertEqual(e1.sequence, 1)
        self.assertEqual(e1.prev_hash, e0.integrity_hash)  # chained

    def test_verify_clean_chain(self):
        for i in range(5):
            record_action(action=f"act.{i}", school_id=self.school.id)
        res = verify_chain(school_id=self.school.id)
        self.assertTrue(res["ok"])
        self.assertEqual(res["checked"], 5)

    def test_tamper_payload_detected(self):
        record_action(action="a", school_id=self.school.id)
        target = record_action(action="b", resource="r", school_id=self.school.id)
        record_action(action="c", school_id=self.school.id)
        # tamper bypassing the append-only save() via queryset.update()
        NonRepudiationLogEntry.objects.filter(pk=target.pk).update(resource="HACKED")
        res = verify_chain(school_id=self.school.id)
        self.assertFalse(res["ok"])
        self.assertEqual(res["broken_at"], target.sequence)
        self.assertEqual(res["reason"], "hash mismatch")

    def test_tamper_signature_detected(self):
        target = record_action(action="a", school_id=self.school.id)
        NonRepudiationLogEntry.objects.filter(pk=target.pk).update(signature="deadbeef")
        res = verify_chain(school_id=self.school.id)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "signature mismatch")

    def test_append_only_enforced(self):
        entry = record_action(action="a", school_id=self.school.id)
        entry.resource = "x"
        with self.assertRaises(NonRepudiationLogReadOnlyError):
            entry.save()
        with self.assertRaises(NonRepudiationLogReadOnlyError):
            entry.delete()

    def test_sensitive_keys_stripped(self):
        entry = record_action(
            action="login",
            school_id=self.school.id,
            payload_summary={"user": "u1", "password": "p", "token": "t"},
        )
        self.assertIn("user", entry.payload_summary)
        self.assertNotIn("password", entry.payload_summary)
        self.assertNotIn("token", entry.payload_summary)

    def test_chains_are_per_school(self):
        other = School.objects.create(
            name="NR2", slug=f"nr2-{uuid.uuid4().hex[:6]}", subdomain=f"nr2{uuid.uuid4().hex[:6]}", is_active=True
        )
        record_action(action="a", school_id=self.school.id)
        e_other = record_action(action="a", school_id=other.id)
        self.assertEqual(e_other.sequence, 0)  # independent chain
        self.assertEqual(e_other.prev_hash, "genesis")
