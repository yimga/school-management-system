"""BR-12: super_views_ai re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsAiReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_ai_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_ai as ai

        self.assertIs(super_views.ai_model_hub, ai.ai_model_hub)
        self.assertIs(super_views.global_ai_version, ai.global_ai_version)
        self.assertIs(super_views.global_ai_version_progress, ai.global_ai_version_progress)
