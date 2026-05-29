"""v4.00.36 — bridge from GradeScaleRegistry.family to bulk_gradebook kind."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.registries.grade_scale_resolver import resolve_grade_scale_kind_for_tenant


class ResolveKindTests(SimpleTestCase):
    def test_returns_default_when_no_school(self):
        self.assertEqual(resolve_grade_scale_kind_for_tenant(None), "percent")

    def test_returns_default_when_no_row(self):
        with mock.patch(
            "apps.registries.grade_scale_resolver.resolve_grade_scale_for_tenant",
            return_value=None,
        ):
            self.assertEqual(
                resolve_grade_scale_kind_for_tenant(mock.Mock(), default_kind="points"),
                "points",
            )

    def test_numeric_family_maps_to_percent(self):
        row = mock.Mock()
        row.family = "numeric"
        with mock.patch(
            "apps.registries.grade_scale_resolver.resolve_grade_scale_for_tenant",
            return_value=row,
        ):
            self.assertEqual(resolve_grade_scale_kind_for_tenant(mock.Mock()), "percent")

    def test_letter_family_maps_to_letter(self):
        row = mock.Mock()
        row.family = "letter"
        with mock.patch(
            "apps.registries.grade_scale_resolver.resolve_grade_scale_for_tenant",
            return_value=row,
        ):
            self.assertEqual(resolve_grade_scale_kind_for_tenant(mock.Mock()), "letter")

    def test_gpa_family_maps_to_gpa4(self):
        row = mock.Mock()
        row.family = "GPA"
        with mock.patch(
            "apps.registries.grade_scale_resolver.resolve_grade_scale_for_tenant",
            return_value=row,
        ):
            self.assertEqual(resolve_grade_scale_kind_for_tenant(mock.Mock()), "gpa4")

    def test_unknown_family_returns_default(self):
        row = mock.Mock()
        row.family = "competency-rubric-2026"
        with mock.patch(
            "apps.registries.grade_scale_resolver.resolve_grade_scale_for_tenant",
            return_value=row,
        ):
            self.assertEqual(
                resolve_grade_scale_kind_for_tenant(mock.Mock(), default_kind="points"),
                "points",
            )
