"""Operational report entity registry — catalog coverage + fail-closed CUSTOM."""

from __future__ import annotations

from django.test import TestCase, tag

from apps.accounts.models import User
from apps.reports.adhoc_runner import run_adhoc_report
from apps.reports.bi_models import AdHocReportDefinition
from apps.reports.report_entity_registry import (
    REPORTABLE_ENTITIES,
    resolve_entity,
)
from apps.schools.models import School
from apps.schools.rls_context import rls_bypass
from apps.siteconfig.models import RegionConfig


@tag("tenants_rls")
class ReportEntityRegistryTests(TestCase):
    def setUp(self):
        with rls_bypass():
            self.user = User.objects.create_user(
                username="report-entity-1811",
                password="pass12345long",
            )
            self.region = RegionConfig.get_default()
            self.school = School.objects.create(
                slug="report-entity-1811",
                subdomain="report-entity-1811",
                name="Report Entity School",
                default_region=self.region,
                timezone=self.region.timezone,
            )

    def test_catalog_aliases_resolve(self):
        self.assertEqual(resolve_entity("STUDENTS").code, "student")
        self.assertEqual(resolve_entity("FINANCE").code, "invoice")
        self.assertEqual(resolve_entity("people.StudentProfile").code, "student")
        self.assertEqual(resolve_entity("evals.Grade").code, "grade")
        self.assertEqual(resolve_entity("evals.Evaluation").model_label, "evals.Evaluation")

    def test_denied_entities_are_explicit(self):
        person = resolve_entity("person")
        self.assertFalse(person.runnable)
        self.assertIn("shared-auth", person.deny_reason)
        section = resolve_entity("section")
        self.assertFalse(section.runnable)
        self.assertIn("catalog-stale", section.deny_reason)

    def test_every_registry_row_has_unique_code(self):
        codes = [e.code for e in REPORTABLE_ENTITIES]
        self.assertEqual(len(codes), len(set(codes)))

    def test_custom_without_entity_code_fails_closed(self):
        with rls_bypass():
            definition = AdHocReportDefinition.objects.create(
                name="Custom dump",
                entity_type="CUSTOM",
                columns=["id", "first_name"],
                school=self.school,
                created_by=self.user,
                output_format="JSON",
            )
        _csv, rows, count, error = run_adhoc_report(
            definition, self.user, output_format="JSON"
        )
        self.assertIsNone(rows)
        self.assertEqual(count, 0)
        self.assertIn("entity_code", error or "")

    def test_custom_unknown_entity_fails_closed(self):
        with rls_bypass():
            definition = AdHocReportDefinition.objects.create(
                name="Unknown",
                entity_type="CUSTOM",
                columns=["id"],
                filters={"entity_code": "not_a_real_entity"},
                school=self.school,
                created_by=self.user,
                output_format="JSON",
            )
        _csv, rows, count, error = run_adhoc_report(
            definition, self.user, output_format="JSON"
        )
        self.assertIsNone(rows)
        self.assertEqual(count, 0)
        self.assertIn("unknown report entity", error or "")

    def test_custom_inventory_runs_empty_for_school(self):
        with rls_bypass():
            definition = AdHocReportDefinition.objects.create(
                name="Inventory",
                entity_type="CUSTOM",
                columns=["id", "name", "quantity"],
                filters={"entity_code": "inventory"},
                school=self.school,
                created_by=self.user,
                output_format="JSON",
            )
        _csv, rows, count, error = run_adhoc_report(
            definition, self.user, output_format="JSON"
        )
        self.assertIsNone(error)
        self.assertEqual(count, 0)
        self.assertEqual(rows, [])

    def test_denied_person_does_not_dump_users(self):
        with rls_bypass():
            definition = AdHocReportDefinition.objects.create(
                name="People dump",
                entity_type="CUSTOM",
                columns=["id", "username"],
                filters={"entity_code": "person"},
                school=self.school,
                created_by=self.user,
                output_format="JSON",
            )
        _csv, rows, count, error = run_adhoc_report(
            definition, self.user, output_format="JSON"
        )
        self.assertIsNone(rows)
        self.assertEqual(count, 0)
        self.assertIn("not reportable", error or "")
