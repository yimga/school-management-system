from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.siteconfig.models import AIGatewayMetric
from apps.siteconfig.tasks import ai_quality_scorecard_beat


class AIQualityScorecardTests(TestCase):
    def test_ai_quality_scorecard_command_outputs_task_rates(self):
        AIGatewayMetric.objects.create(
            date="2026-03-12",
            tenant_id=None,
            task_type="general_chat",
            tier="ollama",
            cost_class="self_hosted",
            request_count=10,
            total_latency_ms=500.0,
            failure_count=1,
            schema_validation_failures=0,
            review_count=4,
            accepted_count=3,
            manual_correction_count=1,
        )
        out = StringIO()
        call_command("ai_quality_scorecard", "--days", "30", stdout=out)
        text = out.getvalue()
        self.assertIn("general_chat", text)
        self.assertIn("acceptance_rate", text)
        self.assertIn("manual_correction_rate", text)

    @patch("django.core.management.call_command")
    def test_ai_quality_scorecard_beat_runs_aggregate_and_scorecard(self, mock_call):
        ai_quality_scorecard_beat()
        self.assertEqual(mock_call.call_count, 2)
        first = mock_call.call_args_list[0].args[0]
        second = mock_call.call_args_list[1].args[0]
        self.assertEqual(first, "aggregate_ai_metrics")
        self.assertEqual(second, "ai_quality_scorecard")
