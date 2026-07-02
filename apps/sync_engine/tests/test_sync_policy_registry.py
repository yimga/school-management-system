from django.test import SimpleTestCase

from apps.sync_engine.conflict_resolver import resolve_one
from apps.sync_engine.policy_registry import (
    MergeStrategy,
    POLICY_VERSION,
    get_policy,
    is_online_required,
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

    def test_online_required_tier_v2(self):
        # v2 adds the tier the sovereign audit asked for: domains that may not
        # even be QUEUED offline (vs SERVER_AUTHORITATIVE, where an offline
        # attempt is accepted and the server copy wins).
        self.assertGreaterEqual(POLICY_VERSION, 2)
        for entity in (
            "tenant_lifecycle_action",
            "security_credential",
            "payment_settlement",
        ):
            policy = get_policy(entity)
            self.assertEqual(policy.strategy, MergeStrategy.ONLINE_REQUIRED, entity)
            self.assertTrue(policy.protected, entity)
            self.assertTrue(is_online_required(entity), entity)
            with self.assertRaisesMessage(ValueError, "crdt_kind_not_allowed"):
                validate_crdt_kind(entity, "LWW")
        self.assertEqual(normalize_entity("offboarding"), "tenant_lifecycle_action")
        self.assertEqual(normalize_entity("mfa"), "security_credential")
        self.assertEqual(normalize_entity("settlement"), "payment_settlement")
        self.assertFalse(is_online_required("student_note"))

    def test_online_required_resolver_rejects_offline_replay(self):
        decision = resolve_one({"entity": "offboarding"})
        self.assertEqual(decision["action"], "reject_offline")
        self.assertTrue(decision["protected_policy"])
        # A caller-requested downgrade must be override-blocked.
        downgraded = resolve_one(
            {"entity": "payment_settlement"}, strategy=MergeStrategy.CAUSAL_LWW
        )
        self.assertEqual(downgraded["action"], "reject_offline")
        self.assertTrue(downgraded["override_blocked"])
