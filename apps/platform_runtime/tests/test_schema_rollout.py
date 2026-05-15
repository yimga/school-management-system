"""Wave D — G3: schema rollout coordinator tests."""

from __future__ import annotations

from unittest import mock

from django.test import TestCase, override_settings

from apps.platform_runtime.models_rollout import (
    SchemaRollout,
    SchemaRolloutAlias,
)
from apps.platform_runtime.schema_rollout import (
    DANGEROUS_OP_TYPES,
    discover_db_aliases,
    run_rollout,
)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class SchemaRolloutTests(TestCase):
    databases = {"default"}

    def setUp(self):
        SchemaRollout.objects.all().delete()
        SchemaRolloutAlias.objects.all().delete()

    def test_dangerous_op_types_includes_expected(self):
        for op in ("RemoveField", "RenameField", "DeleteModel", "RunSQL"):
            self.assertIn(op, DANGEROUS_OP_TYPES)

    def test_discover_db_aliases_always_includes_default(self):
        aliases = discover_db_aliases()
        self.assertIn("default", aliases)

    def test_dry_run_creates_rollout_record_with_dry_run_status(self):
        with mock.patch("apps.platform_runtime.schema_rollout.find_dangerous_operations", return_value=[]):
            result = run_rollout(dry_run=True, aliases=["default"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "dry_run")
        rollout = SchemaRollout.objects.get(pk=result["rollout_id"])
        self.assertEqual(rollout.status, "dry_run")
        self.assertEqual(rollout.alias_results.count(), 1)

    def test_dangerous_migrations_refused_without_flag(self):
        fake_dangers = [("schools", "0099_drop_thing", "DeleteModel")]
        with mock.patch(
            "apps.platform_runtime.schema_rollout.find_dangerous_operations",
            return_value=fake_dangers,
        ):
            result = run_rollout(aliases=["default"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "dangerous_migrations_present")
        self.assertEqual(SchemaRollout.objects.count(), 0)

    def test_dangerous_migrations_allowed_with_flag(self):
        fake_dangers = [("schools", "0099_drop_thing", "DeleteModel")]
        with mock.patch(
            "apps.platform_runtime.schema_rollout.find_dangerous_operations",
            return_value=fake_dangers,
        ), mock.patch(
            "apps.platform_runtime.schema_rollout._migrate_one",
            return_value=("Operations to perform:", "", True),
        ):
            result = run_rollout(dangerous=True, aliases=["default"])
        self.assertTrue(result["ok"])
        rollout = SchemaRollout.objects.get(pk=result["rollout_id"])
        self.assertTrue(rollout.dangerous_acknowledged)
        self.assertEqual(rollout.status, "succeeded")

    def test_partial_status_when_some_aliases_fail(self):
        outcomes = {"default": ("ok", "", True), "fake_alias": ("", "boom", False)}
        with mock.patch(
            "apps.platform_runtime.schema_rollout.find_dangerous_operations",
            return_value=[],
        ), mock.patch(
            "apps.platform_runtime.schema_rollout._migrate_one",
            side_effect=lambda alias, *, target, dry_run: outcomes[alias],
        ):
            result = run_rollout(aliases=["default", "fake_alias"])
        self.assertFalse(result["ok"])
        rollout = SchemaRollout.objects.get(pk=result["rollout_id"])
        self.assertEqual(rollout.status, "partial")
        results_by_alias = {a.db_alias: a.status for a in rollout.alias_results.all()}
        self.assertEqual(results_by_alias["default"], "applied")
        self.assertEqual(results_by_alias["fake_alias"], "failed")

    def test_rollout_records_duration(self):
        with mock.patch(
            "apps.platform_runtime.schema_rollout.find_dangerous_operations",
            return_value=[],
        ), mock.patch(
            "apps.platform_runtime.schema_rollout._migrate_one",
            return_value=("ok", "", True),
        ):
            result = run_rollout(aliases=["default"])
        rollout = SchemaRollout.objects.get(pk=result["rollout_id"])
        self.assertIsNotNone(rollout.finished_at)
        self.assertGreaterEqual(rollout.duration_seconds or 0, 0)
