"""Tests for multi-region DB routing scaffold (batch 1535)."""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from apps.platform_runtime.dynamic_db_routing import (
    clear_request_db_alias,
    effective_db_alias,
    get_request_db_alias,
    resolve_school_db_alias,
    set_request_db_alias,
)


class DynamicDbRoutingTests(SimpleTestCase):
    def tearDown(self):
        clear_request_db_alias()

    @override_settings(ENABLE_MULTI_REGION=False)
    def test_disabled_returns_none(self):
        school = SimpleNamespace(
            dedicated_db_alias="eu-west",
            regional_cluster="eu-west",
            data_region="EU",
        )
        self.assertIsNone(resolve_school_db_alias(school))

    @override_settings(
        ENABLE_MULTI_REGION=True,
        DATABASES={"default": {}, "eu-west": {}},
    )
    def test_resolves_dedicated_alias(self):
        school = SimpleNamespace(
            dedicated_db_alias="eu-west",
            regional_cluster="",
            data_region="EU",
        )
        self.assertEqual(resolve_school_db_alias(school), "eu-west")

    @override_settings(ENABLE_MULTI_REGION=True, DATABASES={"default": {}})
    def test_thread_local_override(self):
        set_request_db_alias("default")
        self.assertEqual(get_request_db_alias(), "default")
        self.assertEqual(effective_db_alias(), "default")
        clear_request_db_alias()
        self.assertIsNone(get_request_db_alias())
