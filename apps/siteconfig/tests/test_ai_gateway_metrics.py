from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.siteconfig.models import AIGatewayMetric


class AggregateAIGatewayMetricsCommandTests(TestCase):
    @patch("apps.siteconfig.management.commands.aggregate_ai_metrics.cache")
    def test_aggregates_cost_class_and_review_loop_counts(self, mock_cache):
        agg_date = "2026-03-12"
        cache_key = f"ai:metrics:{agg_date}:global:setup_recommend:ollama:self_hosted"
        mock_cache.iter_keys.return_value = [cache_key]
        mock_cache.get.return_value = {
            "count": 3,
            "latency_sum": 450.0,
            "failures": 1,
            "schema_fail": 1,
            "review_count": 2,
            "accepted_count": 1,
            "manual_correction_count": 1,
        }

        stdout = StringIO()
        call_command("aggregate_ai_metrics", "--date", agg_date, "--no-delete", stdout=stdout)

        metric = AIGatewayMetric.objects.get(
            date=agg_date,
            tenant_id=None,
            task_type="setup_recommend",
            tier="ollama",
            cost_class="self_hosted",
        )
        self.assertEqual(metric.request_count, 3)
        self.assertEqual(metric.total_latency_ms, 450.0)
        self.assertEqual(metric.failure_count, 1)
        self.assertEqual(metric.schema_validation_failures, 1)
        self.assertEqual(metric.review_count, 2)
        self.assertEqual(metric.accepted_count, 1)
        self.assertEqual(metric.manual_correction_count, 1)
