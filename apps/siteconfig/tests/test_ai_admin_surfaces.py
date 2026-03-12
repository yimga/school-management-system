from django.test import SimpleTestCase

from apps.siteconfig.models import AIGatewayMetric, AIEmbeddingStore, AIPromptRegistry
from config.admin import platform_admin_site


class AIGovernanceAdminTests(SimpleTestCase):
    def test_platform_admin_registers_ai_governance_models(self):
        registry = platform_admin_site._registry
        self.assertIn(AIPromptRegistry, registry)
        self.assertIn(AIEmbeddingStore, registry)
        self.assertIn(AIGatewayMetric, registry)

    def test_ai_metric_admin_exposes_review_loop_fields(self):
        metric_admin = platform_admin_site._registry[AIGatewayMetric]
        self.assertIn("cost_class", metric_admin.list_display)
        self.assertIn("acceptance_rate", metric_admin.list_display)
        self.assertIn("manual_correction_rate", metric_admin.list_display)
