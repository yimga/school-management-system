from django.test import SimpleTestCase

from apps.sync_engine.policy_registry import (
    MergeStrategy,
    POLICY_VERSION,
    get_policy,
    normalize_entity,
    validate_crdt_kind,
)


class SyncPolicyRegistryTests(SimpleTestCase):
    def test_aliases_resolve_to_one_canonical_policy(self):
        self.assertEqual(normalize_entity("grade"), "grade_entry")
        self.assertEqual(normalize_entity("attendance"), "attendance_record")

    def test_protected_domains_fail_closed(self):
        for entity in (
            "grade_entry",
            "fee_payment",
            "invoice_line",
            "user_profile",
            "permission_grant",
        ):
            self.assertTrue(get_policy(entity).protected, entity)

    def test_unknown_entity_is_protected_manual_review(self):
        policy = get_policy("new_unregistered_domain")
        self.assertTrue(policy.protected)
        self.assertEqual(policy.strategy, MergeStrategy.MANUAL_REVIEW)

    def test_crdt_kind_is_limited_by_entity(self):
        self.assertEqual(
            validate_crdt_kind("student_note", "LWW").entity,
            "student_note",
        )
        with self.assertRaisesMessage(ValueError, "crdt_kind_not_allowed"):
            validate_crdt_kind("grade_entry", "LWW")
        with self.assertRaisesMessage(ValueError, "crdt_kind_not_allowed"):
            validate_crdt_kind("attendance_record", "LWW")
        with self.assertRaisesMessage(ValueError, "crdt_kind_not_allowed"):
            validate_crdt_kind("telemetry_counter", "ORSET-ADD")

    def test_policy_version_is_positive(self):
        self.assertGreaterEqual(POLICY_VERSION, 1)
