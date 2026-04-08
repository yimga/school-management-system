"""Guard RuntimeDefaults sync against row-metadata owner filters."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.platform_runtime.models import RuntimeDefaults
from apps.platform_runtime.runtime_sync_owner_filters import (
    NON_PAYLOAD_SYNC_OWNERS,
    RUNTIME_SYNC_OWNER_CHOICES,
    normalize_runtime_sync_owner_filters,
    resolve_runtime_sync_owner_scope,
)


class RuntimeSyncOwnerFilterTests(SimpleTestCase):
    def _site_settings_stub(self) -> object:
        class SiteSettingsStub:
            site_name = "Unsaved Brand"
            enable_offline_mode = True
            backend_feature_flags = {"enable_api_center": True}

            def owned_payload(self, owner=None, exclude_owners=None):
                payload_by_owner = {
                    "brand_experience": {"site_name": self.site_name},
                    "policies_rules": {
                        "enable_offline_mode": self.enable_offline_mode,
                        "backend_feature_flags": dict(self.backend_feature_flags),
                    },
                }
                if owner is not None:
                    return dict(payload_by_owner.get(owner, {}))

                payload = {
                    "site_name": self.site_name,
                    "enable_offline_mode": self.enable_offline_mode,
                    "backend_feature_flags": dict(self.backend_feature_flags),
                }
                for excluded_owner in exclude_owners or ():
                    for field_name in self.owned_field_names(owner=excluded_owner):
                        payload.pop(field_name, None)
                return payload

            def owned_field_names(self, owner=None):
                return {
                    "brand_experience": ("site_name",),
                    "policies_rules": (
                        "enable_offline_mode",
                        "backend_feature_flags",
                    ),
                }.get(owner, ())

        return SiteSettingsStub()

    def _existing_runtime_defaults_stub(self) -> object:
        return SimpleNamespace(
            payload={
                "site_name": "Persisted Brand",
                "enable_offline_mode": False,
                "backend_feature_flags": {"enable_api_center": False},
            },
            site_name="Persisted Brand",
            enable_offline_mode=False,
            backend_feature_flags={"enable_api_center": False},
            save=Mock(),
        )

    def test_non_payload_sync_owner_registry_is_delete_only(self) -> None:
        self.assertEqual(NON_PAYLOAD_SYNC_OWNERS, frozenset({"delete"}))

    def test_normalize_runtime_sync_owner_filters_rejects_delete_owner(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            normalize_runtime_sync_owner_filters(["delete"], None)

        self.assertIn("delete", str(ctx.exception))

    def test_normalize_runtime_sync_owner_filters_rejects_delete_exclusion(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            normalize_runtime_sync_owner_filters(None, ["delete"])

        self.assertIn("delete", str(ctx.exception))

    def test_normalize_runtime_sync_owner_filters_rejects_unknown_owner(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            normalize_runtime_sync_owner_filters(["not_a_real_owner"], None)

        self.assertIn("unknown owners", str(ctx.exception))
        self.assertIn("not_a_real_owner", str(ctx.exception))

    def test_normalize_runtime_sync_owner_filters_rejects_empty_scope(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            normalize_runtime_sync_owner_filters(
                None,
                list(RUNTIME_SYNC_OWNER_CHOICES),
            )

        self.assertIn("exclude every syncable owner", str(ctx.exception))

    def test_runtime_defaults_sync_rejects_delete_owner_filter(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            RuntimeDefaults.sync_from_site_settings(object(), owners=("delete",))

        self.assertIn("delete", str(ctx.exception))

    def test_resolve_runtime_sync_owner_scope_preserves_excluded_owners(self) -> None:
        owners, exclude_owners = normalize_runtime_sync_owner_filters(
            None,
            ["brand_experience"],
        )

        scope = resolve_runtime_sync_owner_scope(owners, exclude_owners)

        self.assertIn("policies_rules", scope)
        self.assertNotIn("brand_experience", scope)
        self.assertNotIn("delete", scope)

    def test_scoped_sync_preserves_unscoped_first_class_columns(self) -> None:
        site_settings = self._site_settings_stub()
        runtime_defaults = self._existing_runtime_defaults_stub()

        with patch.object(
            RuntimeDefaults.objects,
            "get_or_create",
            return_value=(runtime_defaults, False),
        ):
            RuntimeDefaults.sync_from_site_settings(
                site_settings,
                owners=("policies_rules",),
            )

        self.assertEqual(runtime_defaults.site_name, "Persisted Brand")
        self.assertTrue(runtime_defaults.enable_offline_mode)
        self.assertEqual(
            runtime_defaults.backend_feature_flags,
            {"enable_api_center": True},
        )
        self.assertEqual(runtime_defaults.payload, {})
        self.assertNotIn("site_name", runtime_defaults.save.call_args.kwargs["update_fields"])

    def test_excluded_owner_scope_preserves_existing_first_class_columns(self) -> None:
        site_settings = self._site_settings_stub()
        runtime_defaults = self._existing_runtime_defaults_stub()

        with patch.object(
            RuntimeDefaults.objects,
            "get_or_create",
            return_value=(runtime_defaults, False),
        ):
            RuntimeDefaults.sync_from_site_settings(
                site_settings,
                exclude_owners=("brand_experience",),
            )

        self.assertEqual(runtime_defaults.site_name, "Persisted Brand")
        self.assertTrue(runtime_defaults.enable_offline_mode)
        self.assertEqual(runtime_defaults.payload, {})
        self.assertNotIn("site_name", runtime_defaults.save.call_args.kwargs["update_fields"])

    def test_build_payload_from_site_settings_excludes_delete_bucket_by_default(self) -> None:
        calls: list[SimpleNamespace] = []

        class SiteSettingsStub:
            def owned_payload(self, owner=None, exclude_owners=None):
                calls.append(
                    SimpleNamespace(owner=owner, exclude_owners=set(exclude_owners or set()))
                )
                return {}

        RuntimeDefaults.build_payload_from_site_settings(SiteSettingsStub())

        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0].owner)
        self.assertEqual(calls[0].exclude_owners, {"delete"})
