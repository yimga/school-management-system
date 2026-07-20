"""P0-A — Migration Cloud must resolve tenant schema from Client, not School.attr."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase


class ResolveSchoolSchemaNameTests(SimpleTestCase):
    def test_none_school_returns_empty(self):
        from apps.migration_cloud.schema_binding import resolve_school_schema_name

        self.assertEqual(resolve_school_schema_name(None), "")

    def test_uses_get_schema_name_when_available(self):
        from apps.migration_cloud.schema_binding import resolve_school_schema_name

        school = SimpleNamespace(pk=42, slug="new-school")
        with mock.patch(
            "apps.schools.tenant_offboarding.get_schema_name",
            return_value="s_deadbeefcafebabe",
        ):
            self.assertEqual(resolve_school_schema_name(school), "s_deadbeefcafebabe")

    def test_does_not_trust_missing_school_attribute(self):
        """School has no schema_name field — empty getattr must not be the final answer."""
        from apps.migration_cloud.schema_binding import resolve_school_schema_name

        school = SimpleNamespace(pk=7, slug="new-school")  # no schema_name attr
        with mock.patch(
            "apps.schools.tenant_offboarding.get_schema_name",
            return_value=None,
        ), mock.patch(
            "apps.customers.models.Client.objects.filter",
        ) as filt:
            qs = mock.Mock()
            qs.only.return_value.first.return_value = SimpleNamespace(
                schema_name="s_from_client"
            )
            filt.return_value = qs
            self.assertEqual(resolve_school_schema_name(school), "s_from_client")


class EnsureBundleSchemaNameTests(SimpleTestCase):
    def test_fills_empty_schema_from_school(self):
        from apps.migration_cloud.schema_binding import ensure_bundle_schema_name

        school = SimpleNamespace(pk=1)
        bundle = SimpleNamespace(
            schema_name="",
            school=school,
            school_id=1,
            save=mock.Mock(),
        )
        with mock.patch(
            "apps.migration_cloud.schema_binding.resolve_school_schema_name",
            return_value="s_abc",
        ):
            self.assertEqual(ensure_bundle_schema_name(bundle), "s_abc")
        self.assertEqual(bundle.schema_name, "s_abc")
        bundle.save.assert_called_once()

    def test_preserves_existing_schema(self):
        from apps.migration_cloud.schema_binding import ensure_bundle_schema_name

        bundle = SimpleNamespace(
            schema_name="s_already",
            school=SimpleNamespace(pk=1),
            school_id=1,
            save=mock.Mock(),
        )
        self.assertEqual(ensure_bundle_schema_name(bundle), "s_already")
        bundle.save.assert_not_called()
