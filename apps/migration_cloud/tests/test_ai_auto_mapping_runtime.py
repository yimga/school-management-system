"""Runtime tests for apps.migration_cloud.ai_auto_mapping (batch 1493)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud.ai_auto_mapping import (
    AutoMappingError,
    confirm_proposal,
    propose_mappings,
)


class AIAutoMappingRuntimeTests(SimpleTestCase):
    def test_propose_returns_high_confidence_for_exact_match(self) -> None:
        bundle = propose_mappings(source_keys=["first_name", "phone"])
        by_src = {p.source_key: p for p in bundle.proposals}
        self.assertEqual(by_src["first_name"].canonical_key, "identity.given_name")
        self.assertGreaterEqual(by_src["first_name"].confidence, 0.8)
        self.assertEqual(by_src["phone"].canonical_key, "contact.primary_phone")

    def test_credential_keys_are_rejected_not_mapped(self) -> None:
        bundle = propose_mappings(source_keys=["password", "api_key", "first_name"])
        self.assertIn("password", bundle.rejected_keys)
        self.assertIn("api_key", bundle.rejected_keys)
        kept = [p.source_key for p in bundle.proposals]
        self.assertEqual(kept, ["first_name"])

    def test_unknown_field_marked_for_review(self) -> None:
        bundle = propose_mappings(source_keys=["custom_qualia_score"])
        self.assertEqual(len(bundle.proposals), 1)
        p = bundle.proposals[0]
        self.assertEqual(p.canonical_key, "")
        self.assertTrue(p.human_review_required)

    def test_confirm_requires_actor(self) -> None:
        bundle = propose_mappings(source_keys=["first_name"])
        with self.assertRaises(AutoMappingError):
            confirm_proposal(proposal=bundle.proposals[0], approving_actor_id="")

    def test_confirm_returns_hashed_actor(self) -> None:
        bundle = propose_mappings(source_keys=["first_name"])
        rec = confirm_proposal(proposal=bundle.proposals[0], approving_actor_id="user-1")
        self.assertNotEqual(rec["approved_by_hash"], "user-1")
        self.assertEqual(len(rec["approved_by_hash"]), 12)
