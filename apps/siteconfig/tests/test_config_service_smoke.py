"""Smoke tests for modular config facade."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from apps.siteconfig.config_service import (
    BrandConfig,
    GuidedConfigurationWorkflow,
    build_guided_configuration_cards,
)


class ConfigServiceSmokeTests(unittest.TestCase):
    def test_brand_config_dataclass(self) -> None:
        b = BrandConfig(
            values={"primary_color": "#fff"},
            workflow=GuidedConfigurationWorkflow(current_state="Brand ready"),
        )
        self.assertEqual(b.key, "brand")

    def test_guided_cards_request_shim(self) -> None:
        req = MagicMock()
        req.school = None
        req.user = MagicMock()
        req.user.is_staff = False
        cards = build_guided_configuration_cards(req)
        self.assertGreaterEqual(len(cards), 1)
        self.assertIn("domain", cards[0])
        self.assertIn("safe_fix_label", cards[0])
