"""v4.00.36 — unit tests for the tenant grade-scale resolver."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.registries.grade_scale_resolver import resolve_grade_scale_for_tenant


class ResolveGradeScaleForTenantTests(SimpleTestCase):
    def test_none_school_returns_none(self):
        self.assertIsNone(resolve_grade_scale_for_tenant(None))

    def test_exact_context_override_wins(self):
        school = mock.Mock(country_code="FR")
        scale = mock.Mock(is_active=True)
        override = mock.Mock(
            grade_scale=scale, effective_from=None, effective_until=None
        )
        with mock.patch(
            "apps.registries.models.TenantGradeScaleOverride.objects"
        ) as override_objects:
            override_objects.filter.return_value.select_related.return_value.first.return_value = (
                override
            )
            result = resolve_grade_scale_for_tenant(school, context_key="primary")
        self.assertEqual(result, scale)

    def test_inactive_scale_falls_through(self):
        school = mock.Mock(country_code="")
        inactive_scale = mock.Mock(is_active=False)
        override = mock.Mock(
            grade_scale=inactive_scale, effective_from=None, effective_until=None
        )
        with mock.patch(
            "apps.registries.models.TenantGradeScaleOverride.objects"
        ) as override_objects, mock.patch(
            "apps.platform_runtime.models.RuntimeDefaults.objects"
        ) as runtime_objects:
            override_objects.filter.return_value.select_related.return_value.first.return_value = (
                override
            )
            runtime_objects.only.return_value.first.return_value = None
            result = resolve_grade_scale_for_tenant(school)
        self.assertIsNone(result)
