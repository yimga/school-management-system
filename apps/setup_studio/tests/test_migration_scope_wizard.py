"""Migration scope wizard — platform-wide resolver + zero-friction wiring."""

from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio import wizard_engine
from apps.setup_studio.migration_scope import (
    MIGRATION_SCOPE_PRESETS,
    build_migration_scope_choices,
    presets_for_template,
)
from apps.setup_studio.wizard_resolvers_operator import (
    list_migration_scope_choices,
    write_account_migration_step,
)


class MigrationScopeChoicesTests(SimpleTestCase):
    def test_build_migration_scope_choices_non_empty(self):
        choices = build_migration_scope_choices()
        self.assertGreaterEqual(len(choices), 20)
        values = {c["value"] for c in choices}
        self.assertIn("students", values)
        self.assertIn("staff", values)
        self.assertIn("sections", values)
        for choice in choices:
            self.assertIn("label_token", choice)
            self.assertIn("metadata", choice)
            self.assertIn("unlocks", choice["metadata"])

    def test_resolver_matches_builder(self):
        rf = RequestFactory()
        request = rf.get("/")
        choices = list_migration_scope_choices(request=request, school=None)
        self.assertEqual(len(choices), len(build_migration_scope_choices()))

    def test_presets_include_roster_starter(self):
        presets = presets_for_template()
        keys = {p["key"] for p in presets}
        self.assertIn("roster_starter", keys)
        roster = next(p for p in presets if p["key"] == "roster_starter")
        self.assertEqual(roster["domains"], list(MIGRATION_SCOPE_PRESETS[0]["domains"]))


class AccountMigrationScopeRegistryTests(SimpleTestCase):
    def test_select_scope_has_options_resolver(self):
        wizard_engine.load_wizard_registry()
        wizard = wizard_engine.get_wizard("account_migration")
        self.assertIsNotNone(wizard)
        step = next(s for s in wizard.steps if s.key == "select_scope")
        self.assertIsNotNone(step.options_resolver)
        self.assertIn("list_migration_scope_choices", step.options_resolver)


class AccountMigrationScopeWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Scope School",
            slug="scope-school",
            subdomain="scope-school",
            country_code="CM",
            is_active=True,
        )

    def test_write_select_scope_persists_domains(self):
        write_account_migration_step(
            school=self.school,
            wizard_key="account_migration",
            step_key="select_scope",
            payload={"value": ["students", "staff", "sections"]},
            actor_user_id=None,
        )
        self.school.refresh_from_db()
        mc = (self.school.settings or {}).get("migration_cloud", {})
        raw = mc.get("wizard_scope_domains", "")
        self.assertIn("students", raw)
        self.assertIn("sections", raw)
