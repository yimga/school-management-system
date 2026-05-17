"""Tests for v3.6 — operator-environment closeouts as code.

  - Sentry alert-rules-as-code shape + export-cmd output formats
  - Brand-asset manifest + sprite-symbol audit
  - apply_marketplace_migrations cmd (check-only path)
  - check_marketplace_deps cmd (core vs optional vs anymail tiers)
"""

from __future__ import annotations

import io
import json
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.integrations_marketplace import brand_assets as im_brand
from apps.integrations_marketplace import sentry_alert_rules as im_alerts


# ---------------------------------------------------------------------------
# Sentry alert rules
# ---------------------------------------------------------------------------

class SentryAlertRulesTests(SimpleTestCase):
    def test_rules_have_distinct_names(self):
        names = [r.name for r in im_alerts.ALERT_RULES]
        self.assertEqual(len(names), len(set(names)))

    def test_to_dict_round_trip(self):
        for r in im_alerts.ALERT_RULES:
            d = im_alerts.to_dict(r)
            self.assertEqual(d["name"], r.name)
            self.assertEqual(d["threshold"], r.threshold)
            self.assertGreater(d["window_minutes"], 0)

    def test_all_rules_pin_threshold_and_window(self):
        for r in im_alerts.ALERT_RULES:
            self.assertIsInstance(r.threshold, int)
            self.assertGreater(r.threshold, 0)
            self.assertGreater(r.window_minutes, 0)

    def test_export_human_format_lists_every_rule_name(self):
        buf = io.StringIO()
        call_command("export_sentry_alert_rules", stdout=buf)
        out = buf.getvalue()
        for r in im_alerts.ALERT_RULES:
            self.assertIn(r.name, out)

    def test_export_json_format_is_valid_json(self):
        buf = io.StringIO()
        call_command("export_sentry_alert_rules", "--format=json", stdout=buf)
        parsed = json.loads(buf.getvalue())
        self.assertEqual(len(parsed), len(im_alerts.ALERT_RULES))

    def test_export_sentry_cli_format_includes_each_condition_tag(self):
        buf = io.StringIO()
        call_command("export_sentry_alert_rules", "--format=sentry-cli", stdout=buf)
        out = buf.getvalue()
        for r in im_alerts.ALERT_RULES:
            self.assertIn(r.condition_tag, out)


# ---------------------------------------------------------------------------
# Brand-asset manifest
# ---------------------------------------------------------------------------

class BrandAssetsTests(SimpleTestCase):
    def test_every_registry_connector_has_an_entry_or_is_called_out(self):
        from apps.integrations_marketplace.connector_registry import list_connectors
        assets = {a.slug for a in im_brand.BRAND_ASSETS}
        registry = {c.slug for c in list_connectors()}
        missing_in_manifest = registry - assets
        # NEW connectors landing in the registry should also land in the
        # manifest — this test fails loudly when someone adds a connector
        # without recording its brand-license status.
        self.assertEqual(missing_in_manifest, set(),
            f"connectors missing from brand_assets.BRAND_ASSETS: {missing_in_manifest}")

    def test_sprite_symbol_ids_includes_all_9_categories(self):
        ids = im_brand.sprite_symbol_ids()
        for cat in ("meeting", "calendar", "mailbox", "transactional_mail",
                    "chat", "messaging", "payment", "lms", "badges"):
            self.assertIn(f"integration-cat-{cat}", ids,
                f"category glyph integration-cat-{cat} missing from sprite")

    def test_report_separates_slug_glyphs_from_category_fallback(self):
        r = im_brand.report()
        # All connectors today use the category fallback (we ship 9 category
        # glyphs only; no slug-specific glyphs yet). Test asserts that
        # the report's accounting adds up.
        self.assertEqual(
            r["total_connectors"],
            len(r["with_slug_glyph"]) + len(r["category_fallback_only"]),
        )

    def test_check_brand_assets_cmd_runs(self):
        buf = io.StringIO()
        call_command("check_brand_assets", stdout=buf)
        out = buf.getvalue()
        self.assertIn("Total connectors:", out)
        self.assertIn("Category fallback only:", out)

    def test_check_brand_assets_json_format(self):
        buf = io.StringIO()
        call_command("check_brand_assets", "--json", stdout=buf)
        parsed = json.loads(buf.getvalue())
        self.assertIn("total_connectors", parsed)
        self.assertIn("category_fallback_only", parsed)


# ---------------------------------------------------------------------------
# apply_marketplace_migrations cmd
# ---------------------------------------------------------------------------

class ApplyMarketplaceMigrationsTests(SimpleTestCase):
    def test_check_only_does_not_call_migrate(self):
        # Stub showmigrations to report 0175 as already applied.
        def fake_showmigrations(*args, **kwargs):
            stdout = kwargs.get("stdout")
            if stdout is not None:
                stdout.write("[X] 0175_serviceintegration_campus_and_connector_slug\n")

        with mock.patch(
            "apps.integrations_marketplace.management.commands."
            "apply_marketplace_migrations.call_command",
            side_effect=fake_showmigrations,
        ) as cc:
            call_command(
                "apply_marketplace_migrations",
                "--check-only",
                "--schema=acme",
                stdout=io.StringIO(),
            )
        # showmigrations called; migrate_schemas NOT called.
        called_subcommands = [c.args[0] for c in cc.call_args_list]
        self.assertNotIn("migrate_schemas", called_subcommands)
        self.assertNotIn("migrate", called_subcommands)
        self.assertIn("showmigrations", called_subcommands)

    def test_skips_already_applied_schemas(self):
        def fake_call(subcmd, *args, **kwargs):
            stdout = kwargs.get("stdout")
            if subcmd == "showmigrations" and stdout is not None:
                stdout.write("[X] 0175_x\n")

        buf = io.StringIO()
        with mock.patch(
            "apps.integrations_marketplace.management.commands."
            "apply_marketplace_migrations.call_command",
            side_effect=fake_call,
        ) as cc:
            call_command(
                "apply_marketplace_migrations",
                "--schema=acme,beta",
                stdout=buf,
            )
        # Only showmigrations should have been called — migrate_schemas
        # is skipped because 0175 is already applied.
        subcommands = [c.args[0] for c in cc.call_args_list]
        self.assertNotIn("migrate_schemas", subcommands)
        self.assertNotIn("migrate", subcommands)
        out = buf.getvalue()
        self.assertIn("already applied: 2", out)


# ---------------------------------------------------------------------------
# check_marketplace_deps cmd
# ---------------------------------------------------------------------------

class CheckMarketplaceDepsTests(SimpleTestCase):
    def test_command_runs_in_json_format(self):
        buf = io.StringIO()
        try:
            call_command("check_marketplace_deps", "--json", stdout=buf)
        except SystemExit:
            # Strict-mode exit-1 is acceptable for the json shape test.
            pass
        out = buf.getvalue()
        # json shape must be a list of dicts with module + tier + ok keys
        parsed = json.loads(out)
        self.assertIsInstance(parsed, list)
        self.assertGreater(len(parsed), 0)
        for r in parsed:
            self.assertIn("module", r)
            self.assertIn("tier", r)
            self.assertIn("ok", r)

    def test_strict_mode_exits_nonzero_when_optional_missing(self):
        # Force `redis` to look missing.
        original_check = (
            "apps.integrations_marketplace.management.commands."
            "check_marketplace_deps._check"
        )
        def fake_check(module):
            if module in {"redis", "django_redis"}:
                return False, "simulated-missing"
            return True, ""
        with mock.patch(original_check, side_effect=fake_check):
            with self.assertRaises(SystemExit):
                call_command(
                    "check_marketplace_deps", "--strict", stdout=io.StringIO()
                )

    def test_non_strict_passes_when_only_optional_missing(self):
        original_check = (
            "apps.integrations_marketplace.management.commands."
            "check_marketplace_deps._check"
        )
        def fake_check(module):
            if module in {"redis", "django_redis"}:
                return False, "simulated-missing"
            return True, ""  # core deps OK
        with mock.patch(original_check, side_effect=fake_check):
            # Should NOT raise SystemExit since only optional are missing.
            call_command("check_marketplace_deps", stdout=io.StringIO())
