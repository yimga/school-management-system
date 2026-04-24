"""Owner-scoped first-class columns for RuntimeDefaults sync (Phase B / II.3 contract)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.runtime_defaults_first_class import (
    first_class_field_names_for_runtime_sync,
)


class RuntimeSyncFirstClassScopeTests(SimpleTestCase):
    def test_policies_rules_scope_includes_offline_and_feature_flags_not_brand(self) -> None:
        scoped = first_class_field_names_for_runtime_sync(("policies_rules",))

        self.assertIn("enable_offline_mode", scoped)
        self.assertIn("backend_feature_flags", scoped)
        self.assertNotIn("site_name", scoped)

    def test_brand_experience_scope_includes_site_name_not_offline_mode(self) -> None:
        scoped = first_class_field_names_for_runtime_sync(("brand_experience",))

        self.assertIn("site_name", scoped)
        self.assertNotIn("enable_offline_mode", scoped)

    def test_full_scope_is_all_first_class_fields(self) -> None:
        full = first_class_field_names_for_runtime_sync(None)
        self.assertIn("enable_offline_mode", full)
        self.assertIn("site_name", full)
        self.assertGreater(len(full), 10)
