"""BR-12: super_views_runtime_ops re-exported from super_views."""

from django.test import SimpleTestCase


class SuperViewsRuntimeOpsReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_runtime_ops_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_runtime_ops as ops

        self.assertIs(super_views.super_runtime_inspector, ops.super_runtime_inspector)
        self.assertIs(super_views.super_runtime_truth_hub, ops.super_runtime_truth_hub)
        self.assertIs(
            super_views.super_workflow_simulator, ops.super_workflow_simulator
        )
