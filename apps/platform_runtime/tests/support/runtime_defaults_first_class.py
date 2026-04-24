"""Shared scenarios for RuntimeDefaults first-class secret columns."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.platform_runtime.helpers import (
    get_effective_site_settings,
    get_platform_site_settings_record,
    invalidate_effective_site_settings_cache,
)
from apps.platform_runtime.models import RuntimeDefaults

if TYPE_CHECKING:
    from django.test import TestCase


def assert_site_save_sync_writes_column_not_payload(
    tc: TestCase,
    field: str,
    *,
    sync_value: str,
) -> None:
    site = get_platform_site_settings_record(create=True)
    tc.assertIsNotNone(site)
    site.apply_feature_control_state(field_updates={field: sync_value})
    rd = RuntimeDefaults.get_singleton()
    tc.assertIsNotNone(rd)
    tc.assertEqual(getattr(rd, field), sync_value)
    tc.assertNotIn(field, rd.payload or {})


def assert_effective_settings_use_runtime_column_over_legacy_site(
    tc: TestCase,
    field: str,
    *,
    legacy_site_value: str,
    runtime_column_value: str,
) -> None:
    invalidate_effective_site_settings_cache()
    site = get_platform_site_settings_record(create=True)
    tc.assertIsNotNone(site)
    site.apply_feature_control_state(field_updates={field: legacy_site_value})
    rd = RuntimeDefaults.get_singleton()
    tc.assertIsNotNone(rd)
    setattr(rd, field, runtime_column_value)
    pl = dict(rd.payload or {})
    pl.pop(field, None)
    rd.payload = pl
    rd.save(update_fields=[field, "payload", "updated_at"])
    invalidate_effective_site_settings_cache()
    eff = get_effective_site_settings(request=None, school=None)
    tc.assertIsNotNone(eff)
    tc.assertEqual(getattr(eff, field, None), runtime_column_value)


def assert_sync_strips_field_from_runtime_payload(
    tc: TestCase,
    field: str,
    *,
    canonical_value: str,
    shadow_payload_value: str,
) -> None:
    site = get_platform_site_settings_record(create=True)
    tc.assertIsNotNone(site)
    site.apply_feature_control_state(field_updates={field: canonical_value})
    rd = RuntimeDefaults.get_singleton()
    tc.assertIsNotNone(rd)
    pl = dict(rd.payload or {})
    pl[field] = shadow_payload_value
    rd.payload = pl
    rd.save(update_fields=["payload", "updated_at"])
    RuntimeDefaults.sync_from_site_settings(site)
    rd.refresh_from_db()
    tc.assertEqual(getattr(rd, field), canonical_value)
    tc.assertNotIn(field, rd.payload or {})
