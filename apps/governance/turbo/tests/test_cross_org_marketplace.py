"""Tests for cross_org_marketplace runtime."""

from __future__ import annotations

import unittest

from apps.governance.turbo import cross_org_marketplace as com


class MarketplaceTests(unittest.TestCase):
    def test_isolated_visibility_without_consent(self) -> None:
        market = com.Marketplace()
        market.post_offer(com.Offer("o1", "orgA", "teacher_transfer", {}))
        market.post_offer(com.Offer("o2", "orgB", "curriculum", {}))
        self.assertEqual(len(market.list_offers(requesting_org_id="orgA")), 1)

    def test_visibility_after_consent(self) -> None:
        market = com.Marketplace()
        market.post_offer(com.Offer("o1", "orgB", "teacher_transfer", {}))
        market.grant_consent("orgB", "orgA")
        self.assertEqual(len(market.list_offers(requesting_org_id="orgA")), 1)

    def test_consent_revoke(self) -> None:
        market = com.Marketplace()
        market.post_offer(com.Offer("o1", "orgB", "teacher_transfer", {}))
        market.grant_consent("orgB", "orgA")
        market.revoke_consent("orgB", "orgA")
        self.assertEqual(len(market.list_offers(requesting_org_id="orgA")), 0)
