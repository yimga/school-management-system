"""BR-12: super_views_runtime_ops re-exported from super_views."""

import ast
import inspect

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


class SuperRuntimeTruthHubContractTests(SimpleTestCase):
    """Phase 7: no raw SiteSettings.objects calls in truth hub — use platform helper."""

    def test_truth_hub_uses_get_platform_site_settings_record_not_orm(self):
        from apps.schools.super_views_runtime_ops import super_runtime_truth_hub

        src = inspect.getsource(super_runtime_truth_hub)
        self.assertIn("get_platform_site_settings_record", src)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "objects":
                base = func.value
                if isinstance(base, ast.Name) and base.id == "SiteSettings":
                    self.fail(
                        "super_runtime_truth_hub must not call SiteSettings.objects.*; "
                        "use get_platform_site_settings_record"
                    )
