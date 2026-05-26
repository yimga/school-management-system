"""Depth tests for apps.migration_cloud.ai_auto_mapping (batch 1509)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.migration_cloud.ai_auto_mapping import (
    AutoMappingError,
    MappingProposal,
    confirm_proposal,
    propose_mappings,
)


class AIAutoMappingDepthTests(SimpleTestCase):
    def test_credential_keys_are_rejected_not_proposed(self) -> None:
        bundle = propose_mappings(
            source_keys=[
                "first_name",
                "user_password",
                "API_KEY",
                "private_key",
                "secret_token",
            ],
        )
        rejected = set(bundle.rejected_keys)
        self.assertIn("user_password", rejected)
        self.assertIn("API_KEY", rejected)
        self.assertIn("private_key", rejected)
        self.assertIn("secret_token", rejected)
        # first_name should still be proposed
        proposed_source_keys = {p.source_key for p in bundle.proposals}
        self.assertIn("first_name", proposed_source_keys)

    def test_unmappable_source_key_marked_for_human_review(self) -> None:
        bundle = propose_mappings(source_keys=["completely_unmappable_xyz"])
        self.assertEqual(len(bundle.proposals), 1)
        self.assertTrue(bundle.proposals[0].human_review_required)
        self.assertEqual(bundle.proposals[0].confidence, 0.0)
        self.assertEqual(bundle.proposals[0].canonical_key, "")

    def test_exact_match_yields_high_confidence(self) -> None:
        bundle = propose_mappings(source_keys=["first_name"])
        proposal = bundle.proposals[0]
        self.assertEqual(proposal.canonical_key, "identity.given_name")
        self.assertGreaterEqual(proposal.confidence, 0.8)

    def test_low_confidence_requires_human_review(self) -> None:
        bundle = propose_mappings(
            source_keys=["first_name"],
            confidence_threshold=0.99,
        )
        # With a 0.99 threshold, even the 0.8 heuristic score should require
        # human review.
        proposal = bundle.proposals[0]
        self.assertTrue(proposal.human_review_required)

    def test_confirm_proposal_rejects_blank_actor(self) -> None:
        proposal = MappingProposal(
            source_key="first_name",
            canonical_key="identity.given_name",
            confidence=0.95,
            rationale="exact",
            human_review_required=False,
        )
        with self.assertRaises(AutoMappingError):
            confirm_proposal(proposal=proposal, approving_actor_id="")

    def test_confirm_proposal_rejects_unknown_canonical_key(self) -> None:
        proposal = MappingProposal(
            source_key="x",
            canonical_key="not.a.real.key",
            confidence=1.0,
            rationale="x",
            human_review_required=False,
        )
        with self.assertRaises(AutoMappingError):
            confirm_proposal(proposal=proposal, approving_actor_id="actor-A")

    def test_confirm_proposal_hashes_actor_id(self) -> None:
        proposal = MappingProposal(
            source_key="first_name",
            canonical_key="identity.given_name",
            confidence=0.95,
            rationale="exact",
            human_review_required=False,
        )
        receipt = confirm_proposal(
            proposal=proposal,
            approving_actor_id="actor-distinctive-XYZ",
        )
        self.assertNotIn("actor-distinctive-XYZ", receipt["approved_by_hash"])
        self.assertEqual(len(receipt["approved_by_hash"]), 12)

    def test_log_emission_does_not_echo_raw_credential_key(self) -> None:
        with self.assertLogs("apps.migration_cloud.ai_auto_mapping", level="INFO") as cm:
            propose_mappings(source_keys=["super_distinctive_api_key_name"])
        log_text = "\n".join(cm.output)
        self.assertNotIn("super_distinctive_api_key_name", log_text)

    def test_rationale_does_not_echo_credential_substrings(self) -> None:
        bundle = propose_mappings(
            source_keys=["api_key_hint"],
        )
        # Credentials should be rejected entirely, so no proposal carries the
        # raw token in its rationale.
        self.assertEqual(bundle.rejected_keys, ["api_key_hint"])
        self.assertEqual(bundle.proposals, [])

    def test_bundle_to_dict_round_trips_fields(self) -> None:
        bundle = propose_mappings(source_keys=["first_name", "the_password"])
        d = bundle.to_dict()
        self.assertEqual(len(d["proposals"]), 1)
        self.assertEqual(d["proposals"][0]["source_key"], "first_name")
        self.assertEqual(d["rejected_keys"], ["the_password"])
