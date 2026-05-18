"""Move 3 — PDP / ABAC / DLP tests."""

from __future__ import annotations

from django.test import TestCase

from apps.metadata.models import EntityCatalogEntry, FieldCatalogEntry
from apps.policies import dlp
from apps.policies.models import PolicyDecisionLog, PolicyRule
from apps.policies.pdp import Decision, allowed, decide, require
from apps.schools.models import School


def _make_school(slug="m3s"):
    return School.objects.create(slug=slug, name="M3", subdomain=slug)


class PDPBasicTests(TestCase):
    def test_implicit_deny_when_no_rule(self):
        d = decide({"role": "TEACHER"}, "read", {"entity": "student"})
        self.assertEqual(d.effect, "implicit_deny")
        self.assertIsNone(d.matched_rule_id)

    def test_allow_rule_matches_role(self):
        PolicyRule.objects.create(
            code="teacher_read_student",
            name="Teacher may read students",
            effect=PolicyRule.Effect.ALLOW,
            subject_match={"role": "TEACHER"},
            action_match={"actions": ["read"]},
            resource_match={"entity": "student"},
            priority=10,
        )
        d = decide({"role": "TEACHER"}, "read", {"entity": "student"})
        self.assertEqual(d.effect, "allow")
        self.assertTrue(d.allowed)

    def test_first_matching_rule_wins_by_priority(self):
        PolicyRule.objects.create(
            code="deny_all_default",
            name="Default deny",
            effect=PolicyRule.Effect.DENY,
            subject_match={},
            action_match={"actions": ["*"]},
            priority=999,
        )
        PolicyRule.objects.create(
            code="teacher_read",
            name="Teacher read allowed",
            effect=PolicyRule.Effect.ALLOW,
            subject_match={"role": "TEACHER"},
            action_match={"actions": ["read"]},
            priority=10,
        )
        d = decide({"role": "TEACHER"}, "read", {"entity": "anything"})
        self.assertEqual(d.effect, "allow")

    def test_wildcard_actions_and_role_any(self):
        PolicyRule.objects.create(
            code="staff_any",
            name="Staff can do anything to student",
            effect=PolicyRule.Effect.ALLOW,
            subject_match={"role_any": ["TEACHER", "ADMIN"]},
            action_match={"actions": ["*"]},
            resource_match={"entity": "student"},
            priority=20,
        )
        self.assertTrue(allowed({"role": "ADMIN"}, "write", {"entity": "student"}))
        self.assertTrue(allowed({"role": "TEACHER"}, "delete", {"entity": "student"}))
        # role not in role_any
        d = decide({"role": "STUDENT"}, "read", {"entity": "student"})
        self.assertEqual(d.effect, "implicit_deny")

    def test_conditions_block_match(self):
        PolicyRule.objects.create(
            code="read_own_school",
            name="Read records only in same school",
            effect=PolicyRule.Effect.ALLOW,
            subject_match={"role": "TEACHER"},
            action_match={"actions": ["read"]},
            resource_match={"entity": "student"},
            conditions=[
                {"attr": "subject.school_id", "op": "eq", "value": "$resource.school_id"}
            ],
            priority=10,
        )
        # Same school: pass — but our DSL has no $-substitution; the test verifies condition
        # *fails* when attr=value comparison fails.
        d = decide({"role": "TEACHER", "school_id": "A"}, "read", {"entity": "student", "school_id": "B"})
        self.assertEqual(d.effect, "implicit_deny")

    def test_log_row_written(self):
        PolicyRule.objects.create(
            code="allow_simple",
            name="x",
            effect=PolicyRule.Effect.ALLOW,
            subject_match={"role": "ADMIN"},
            action_match={"actions": ["read"]},
            priority=5,
        )
        decide({"role": "ADMIN", "user_id": 99}, "read", {"entity": "student", "id": 1})
        self.assertTrue(
            PolicyDecisionLog.objects.filter(
                subject_role="ADMIN", action="read", effect="allow"
            ).exists()
        )

    def test_require_raises_permission_denied(self):
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            require({"role": "STUDENT"}, "delete", {"entity": "student"})


class PDPSensitivityTests(TestCase):
    def test_sensitivity_tier_at_or_above_match(self):
        # Rule that DENIES access to fields at confidential+ for students.
        PolicyRule.objects.create(
            code="block_students_confidential",
            name="Students cannot read confidential fields",
            effect=PolicyRule.Effect.DENY,
            subject_match={"role": "STUDENT"},
            action_match={"actions": ["read"]},
            resource_match={"entity": "student", "sensitivity_tier_at_or_above": "confidential"},
            priority=10,
        )
        # Non-sensitive field is implicit-denied (no allow rule) but not by this rule.
        d = decide({"role": "STUDENT"}, "read", {"entity": "student", "field": "preferred_name", "sensitivity_tier": "internal"})
        self.assertEqual(d.effect, "implicit_deny")
        # Confidential field gets explicit deny from the rule.
        d2 = decide({"role": "STUDENT"}, "read", {"entity": "student", "field": "ssn", "sensitivity_tier": "secret"})
        self.assertEqual(d2.effect, "deny")
        self.assertIsNotNone(d2.matched_rule_id)


class DLPFieldRedactionTests(TestCase):
    def setUp(self):
        self.entity = EntityCatalogEntry.objects.create(code="student", name="Student")
        FieldCatalogEntry.objects.create(
            entity=self.entity, field_name="preferred_name",
            data_type="string", sensitivity_tier="public",
        )
        FieldCatalogEntry.objects.create(
            entity=self.entity, field_name="email",
            data_type="string", sensitivity_tier="internal",
            compliance_tags=["pii"], dlp_redaction_strategy="mask",
        )
        FieldCatalogEntry.objects.create(
            entity=self.entity, field_name="ssn",
            data_type="string", sensitivity_tier="secret",
            compliance_tags=["pii", "ferpa"], dlp_redaction_strategy="hash",
        )
        # Allow teachers to read up to confidential.
        PolicyRule.objects.create(
            code="teacher_read_internal",
            name="Teachers may read internal+ down to confidential",
            effect=PolicyRule.Effect.ALLOW,
            subject_match={"role": "TEACHER"},
            action_match={"actions": ["read"]},
            resource_match={"entity": "student"},
            conditions=[
                # No confidential or higher.
                {"attr": "resource.sensitivity_tier", "op": "in",
                 "value": ["public", "internal", "restricted"]}
            ],
            priority=10,
        )

    def test_public_field_passes_through(self):
        record = {"preferred_name": "Sam", "email": "sam@s.test", "ssn": "111-22-3333"}
        out = dlp.redact_record(record, entity="student", subject={"role": "TEACHER"})
        self.assertEqual(out["preferred_name"], "Sam")

    def test_secret_field_redacted_with_strategy(self):
        record = {"preferred_name": "Sam", "email": "sam@s.test", "ssn": "111-22-3333"}
        out = dlp.redact_record(record, entity="student", subject={"role": "TEACHER"})
        self.assertTrue(str(out["ssn"]).startswith("sha256:"))

    def test_iterable_redaction(self):
        records = [
            {"preferred_name": "A", "ssn": "x"},
            {"preferred_name": "B", "ssn": "y"},
        ]
        out = dlp.redact_iterable(records, entity="student", subject={"role": "TEACHER"})
        self.assertEqual(len(out), 2)
        for row in out:
            self.assertTrue(str(row["ssn"]).startswith("sha256:"))
