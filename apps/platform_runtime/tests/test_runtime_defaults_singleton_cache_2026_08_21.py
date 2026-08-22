"""Seal for the RuntimeDefaults query storm.

MEASURED before the fix: one tenant admin changelist (`/admin/accounts/user/`) issued
**8,944** queries, **8,275** of them the same SELECT against
`platform_runtime_runtimedefaults`. Tracing showed 8,118 arriving through
`SiteSettings.__getattr__`, which consults RuntimeDefaults for every behavioural
field Phase B moved off that table -- and `owned_payload()` loops those fields, so the
cost was quadratic. `apps/siteconfig/tests/test_admin_model_outcomes.py` could not
finish in nine minutes; a single changelist took ~53 seconds of server time.

After: 1,286 queries for the same page, and the module completes.

These tests assert the two properties that make the memo safe rather than merely
fast. A cache that cannot be invalidated would be a correctness bug traded for a
performance one, and the admin's own edit-then-read flow is exactly where that would
surface.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.platform_runtime.models import RuntimeDefaults


def _runtime_defaults_queries(captured) -> int:
    return sum(
        1 for q in captured if "platform_runtime_runtimedefaults" in q["sql"].lower()
    )


class RuntimeDefaultsSingletonCacheTests(TestCase):
    def setUp(self):
        RuntimeDefaults.invalidate_singleton_cache()

    def tearDown(self):
        RuntimeDefaults.invalidate_singleton_cache()

    def test_repeated_reads_hit_the_database_once(self):
        """The storm, in miniature: 50 reads used to be 50 queries."""
        RuntimeDefaults.get_singleton()  # prime
        with CaptureQueriesContext(connection) as ctx:
            for _ in range(50):
                RuntimeDefaults.get_singleton()
        self.assertEqual(
            _runtime_defaults_queries(ctx.captured_queries),
            0,
            "every get_singleton() after the first must be served from the memo",
        )

    def test_a_save_is_visible_to_the_very_next_read(self):
        """An admin edits RuntimeDefaults and immediately re-reads it."""
        RuntimeDefaults.get_singleton()  # prime the memo
        row, _ = RuntimeDefaults.objects.get_or_create(pk=1)
        row.payload = {"rmc_cache_seal": "written"}
        row.save()
        fresh = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(fresh)
        self.assertEqual(
            (fresh.payload or {}).get("rmc_cache_seal"),
            "written",
            "save() must invalidate the memo, or the admin shows a stale value",
        )

    def test_a_delete_is_visible_to_the_very_next_read(self):
        RuntimeDefaults.objects.get_or_create(pk=1)
        self.assertIsNotNone(RuntimeDefaults.get_singleton())
        RuntimeDefaults.objects.get(pk=1).delete()
        self.assertIsNone(
            RuntimeDefaults.get_singleton(),
            "delete() must invalidate the memo",
        )

    def test_explicit_invalidation_forces_a_refetch(self):
        RuntimeDefaults.get_singleton()
        RuntimeDefaults.invalidate_singleton_cache()
        with CaptureQueriesContext(connection) as ctx:
            RuntimeDefaults.get_singleton()
        self.assertGreaterEqual(_runtime_defaults_queries(ctx.captured_queries), 1)

    @override_settings(RUNTIME_DEFAULTS_SINGLETON_CACHE_SECONDS=0)
    def test_the_memo_can_be_switched_off_entirely(self):
        RuntimeDefaults.invalidate_singleton_cache()
        RuntimeDefaults.get_singleton()
        with CaptureQueriesContext(connection) as ctx:
            RuntimeDefaults.get_singleton()
            RuntimeDefaults.get_singleton()
        self.assertGreaterEqual(
            _runtime_defaults_queries(ctx.captured_queries),
            2,
            "a zero TTL must disable the memo, not merely shorten it",
        )

    def test_site_settings_attribute_reads_do_not_scale_with_query_count(self):
        """The actual defect: SiteSettings.__getattr__ queried once per attribute."""
        from apps.siteconfig.models import SiteSettings

        settings_row = SiteSettings.objects.first()
        if settings_row is None:
            # Create one rather than skip: this is the assertion that pins the actual
            # defect, and a skipped guard is a guard that never ran.
            settings_row = SiteSettings.objects.create()
        RuntimeDefaults.get_singleton()  # prime
        names = [
            "enable_offline_mode",
            "mfa_enforcement_mode",
            "require_mfa_roles",
            "default_notification_channels",
        ]
        with CaptureQueriesContext(connection) as ctx:
            for _ in range(10):
                for name in names:
                    getattr(settings_row, name, None)
        self.assertEqual(
            _runtime_defaults_queries(ctx.captured_queries),
            0,
            "40 attribute reads used to mean up to 40 RuntimeDefaults queries",
        )
