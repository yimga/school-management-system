"""Offline AI help — sync_engine contract."""

from django.test import SimpleTestCase

from apps.sync_engine.offline_help import (
    enqueue_offline_help_draft,
    offline_help_queue_contract,
)


class OfflineAIHelpContractTests(SimpleTestCase):
    def test_contract_lists_backend(self):
        contract = offline_help_queue_contract()
        self.assertIn("queue_backend", contract)
        self.assertIn("allowed_actions", contract)

    def test_enqueue_returns_contract_surface(self):
        result = enqueue_offline_help_draft(school_id=1, user_id=2, draft_key="help-draft-1")
        self.assertTrue(result["ok"])
        self.assertIn("contract", result)
