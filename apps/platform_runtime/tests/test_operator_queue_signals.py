"""Tests for operator_queue_signals (batch 1526)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.operator_queue_signals import (
    build_operator_queue_smart_link_context,
)
from apps.platform_runtime.smart_links_kernel import (
    STATE_DSL_CONCERN_OPEN,
)


class _Req:
    school = None


class OperatorQueueSignalsTests(SimpleTestCase):
    def test_no_school_returns_empty_state(self) -> None:
        ctx = build_operator_queue_smart_link_context(_Req())
        self.assertEqual(ctx["operator_queue_smart_link_state"], "")

    def test_dsl_precedence_over_admissions(self) -> None:
        class School:
            settings = {
                "safeguarding": {
                    "dsl_inbox": [
                        {"entry_id": "e1", "concern_id": "c1"},
                    ],
                },
            }

        class Req:
            school = School()

        ctx = build_operator_queue_smart_link_context(Req())
        self.assertEqual(ctx["operator_queue_smart_link_state"], STATE_DSL_CONCERN_OPEN)
        self.assertEqual(ctx["operator_queue_dsl_unacknowledged"], 1)
