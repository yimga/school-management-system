"""Tests for metadata precedence chain (plan I3)."""
from django.test import TestCase

from apps.platform_runtime.precedence import (
    PRECEDENCE_ORDER,
    merge_by_precedence,
    precedence_rank,
)


class PrecedenceChainTests(TestCase):
    def test_precedence_order_is_seven_levels(self):
        self.assertEqual(
            PRECEDENCE_ORDER,
            ["platform", "region", "blueprint", "policy_bundle", "plan", "tenant", "sandbox"],
        )

    def test_precedence_rank_increases(self):
        self.assertLess(precedence_rank("platform"), precedence_rank("tenant"))
        self.assertLess(precedence_rank("tenant"), precedence_rank("sandbox"))
        self.assertEqual(precedence_rank("unknown"), -1)

    def test_merge_by_precedence_returns_highest_scope_value(self):
        values = [
            ("platform", "default"),
            ("tenant", "tenant_override"),
            ("region", "region_override"),
        ]
        self.assertEqual(merge_by_precedence(values=values), "tenant_override")

    def test_merge_by_precedence_sandbox_wins(self):
        values = [
            ("platform", "a"),
            ("tenant", "b"),
            ("sandbox", "c"),
        ]
        self.assertEqual(merge_by_precedence(values=values), "c")

    def test_merge_by_precedence_empty_returns_none(self):
        self.assertIsNone(merge_by_precedence(values=[]))
