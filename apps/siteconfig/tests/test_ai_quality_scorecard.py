from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.siteconfig.models import AIGatewayMetric
from apps.siteconfig.tasks import ai_quality_scorecard_beat


class AIQualityScorecardTests(TestCase):
    def test_ai_quality_scorecard_command_outputs_task_rates(self):
        metric_date = date.today() - timedelta(days=1)
        AIGatewayMetric.objects.create(
            date=metric_date,
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

    def test_ai_quality_scorecard_task_type_filter_is_case_normalized(self):
        metric_date = date.today()
        AIGatewayMetric.objects.create(
            date=metric_date,
            tenant_id=None,
            task_type="general_chat",
            tier="ollama",
            cost_class="self_hosted",
            request_count=5,
            total_latency_ms=250.0,
            failure_count=0,
            schema_validation_failures=0,
            review_count=2,
            accepted_count=2,
            manual_correction_count=0,
        )
        AIGatewayMetric.objects.create(
            date=metric_date,
            tenant_id=None,
            task_type="setup_recommend",
            tier="ollama",
            cost_class="self_hosted",
            request_count=3,
            total_latency_ms=150.0,
            failure_count=1,
            schema_validation_failures=0,
            review_count=1,
            accepted_count=1,
            manual_correction_count=0,
        )

        out = StringIO()
        call_command(
            "ai_quality_scorecard",
            "--days",
            "7",
            "--task-type",
            "  GENERAL_CHAT  ",
            stdout=out,
        )

        text = out.getvalue()
        self.assertIn("general_chat", text)
        self.assertNotIn("setup_recommend", text)

    def test_ai_quality_scorecard_days_clamped_to_1_to_30(self):
        metric_date = date.today()
        AIGatewayMetric.objects.create(
            date=metric_date,
            tenant_id=None,
            task_type="general_chat",
            tier="ollama",
            cost_class="self_hosted",
            request_count=1,
            total_latency_ms=100.0,
            failure_count=0,
            schema_validation_failures=0,
            review_count=1,
            accepted_count=1,
            manual_correction_count=0,
        )
        out = StringIO()
        call_command("ai_quality_scorecard", "--days", "0", stdout=out)
        self.assertIn("days=1", out.getvalue())

        out_hi = StringIO()
        call_command("ai_quality_scorecard", "--days", "999", stdout=out_hi)
        self.assertIn("days=30", out_hi.getvalue())

    def test_ai_quality_scorecard_warns_when_window_has_no_metrics(self):
        AIGatewayMetric.objects.create(
            date=date.today() - timedelta(days=40),
            tenant_id=None,
            task_type="general_chat",
            tier="ollama",
            cost_class="self_hosted",
            request_count=2,
            total_latency_ms=120.0,
            failure_count=0,
            schema_validation_failures=0,
            review_count=1,
            accepted_count=1,
            manual_correction_count=0,
        )

        out = StringIO()
        call_command("ai_quality_scorecard", "--days", "7", stdout=out)

        self.assertIn("No AI metrics found for this window.", out.getvalue())

    @patch("django.core.management.call_command")
    def test_ai_quality_scorecard_beat_runs_aggregate_and_scorecard(self, mock_call):
        ai_quality_scorecard_beat()
        self.assertEqual(mock_call.call_count, 2)
        first = mock_call.call_args_list[0].args[0]
        second = mock_call.call_args_list[1].args[0]
        self.assertEqual(first, "aggregate_ai_metrics")
        self.assertEqual(second, "ai_quality_scorecard")
