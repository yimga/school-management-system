"""The operator can see and override how ambiguous dates are read.

``03/04/2010`` is either 3 April or 4 March, and which one it is cannot be
recovered from the value. The engine already resolves this well: the profiler
votes per column using values above 12 as evidence, and the tenant's country
profile fills in when the vote is indecisive.

What was missing is the operator. A school whose file disagrees with its
country's convention -- an export produced by a US-built system, a spreadsheet
retyped from a foreign template -- had no way to see which reading was chosen or
to correct it, and a wrong reading is silent: every date lands, every date is
wrong, and nothing is quarantined to hint at it.

This rides the same ``mapping_summary['transform_prefs']`` channel as the
combined-name order, so the operator's explicit choice outranks both the
profiler's vote and the country default.
"""

from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud.models import MigrationArtifact, MigrationBundle
from apps.migration_cloud.views_tenant_upload import (
    DATE_ORDER_CHOICES,
    date_order_preview,
    selected_date_order,
)
from apps.schools.models import School


class OperatorDateFormatTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Date School", slug="date-school", subdomain="date-school", is_active=True
        )
        self.bundle = MigrationBundle.objects.create(school=self.school)

    def _choose(self, value: str):
        self.bundle.mapping_summary = {"transform_prefs": {"date_order": value}}
        self.bundle.save(update_fields=["mapping_summary"])
        self.bundle.refresh_from_db()

    def test_no_choice_leaves_the_existing_inference_alone(self):
        from apps.migration_cloud.orchestrator import operator_date_format

        self.assertEqual(operator_date_format(self.bundle), "")

    def test_an_unknown_value_is_ignored_rather_than_trusted(self):
        self._choose("nonsense")
        from apps.migration_cloud.orchestrator import operator_date_format

        self.assertEqual(operator_date_format(self.bundle), "")

    def test_day_first_and_month_first_map_to_real_strptime_formats(self):
        from apps.migration_cloud.orchestrator import operator_date_format

        self._choose("day_first")
        self.assertEqual(operator_date_format(self.bundle), "%d/%m/%Y")
        self._choose("month_first")
        self.assertEqual(operator_date_format(self.bundle), "%m/%d/%Y")

    def test_the_choice_outranks_the_profilers_own_vote(self):
        """The whole point: the operator knows something the data does not show."""
        from apps.migration_cloud.orchestrator import apply_operator_date_override

        # The profiler voted day-first from the data.
        hints = {"date_format": "%d/%m/%Y"}
        self._choose("month_first")
        apply_operator_date_override(hints, self.bundle)
        self.assertEqual(hints["date_format"], "%m/%d/%Y")

    def test_no_choice_does_not_disturb_the_vote(self):
        from apps.migration_cloud.orchestrator import apply_operator_date_override

        hints = {"date_format": "%d/%m/%Y"}
        apply_operator_date_override(hints, self.bundle)
        self.assertEqual(hints["date_format"], "%d/%m/%Y")


class DateOrderPreviewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Preview Dates",
            slug="preview-dates",
            subdomain="preview-dates",
            is_active=True,
        )
        self.bundle = MigrationBundle.objects.create(school=self.school)
        MigrationArtifact.objects.create(
            bundle=self.bundle,
            path_within_bundle="students.xlsx",
            filename="students.xlsx",
            sha256="d" * 64,
            locale_hints={},
            profile={
                "columns": [
                    {
                        "name": "Date de naissance",
                        "normalized": "date_de_naissance",
                        "inferred_type": "date",
                        "samples": ["03/04/2010", "05/06/2011"],
                    }
                ]
            },
        )

    def test_preview_uses_the_schools_own_dates(self):
        preview = date_order_preview(self.bundle)
        self.assertEqual(len(preview), len(DATE_ORDER_CHOICES))
        sources = {r["source"] for option in preview for r in option["rows"]}
        self.assertIn("03/04/2010", sources)

    def test_the_two_readings_visibly_differ(self):
        by_value = {o["value"]: o["rows"][0] for o in date_order_preview(self.bundle)}
        self.assertNotEqual(
            by_value["day_first"]["reading"],
            by_value["month_first"]["reading"],
            "both readings previewed identically — the preview cannot inform a choice",
        )

    def test_the_preview_spells_the_month_out(self):
        """'3 April 2010' is unmistakable; '03/04/2010' is the whole problem."""
        by_value = {o["value"]: o["rows"][0] for o in date_order_preview(self.bundle)}
        self.assertIn("April", by_value["day_first"]["reading"])
        self.assertIn("March", by_value["month_first"]["reading"])

    def test_no_preview_when_no_ambiguous_date_column_exists(self):
        MigrationArtifact.objects.filter(bundle=self.bundle).update(
            profile={
                "columns": [
                    {
                        "name": "DOB",
                        "normalized": "dob",
                        "inferred_type": "date",
                        "samples": ["2010-04-03"],
                    }
                ]
            }
        )
        self.assertEqual(
            date_order_preview(self.bundle),
            [],
            "ISO dates are not ambiguous and must not prompt for a choice",
        )

    def test_selection_round_trips(self):
        self.assertEqual(selected_date_order(self.bundle), "")
        self.bundle.mapping_summary = {"transform_prefs": {"date_order": "month_first"}}
        self.bundle.save(update_fields=["mapping_summary"])
        self.bundle.refresh_from_db()
        self.assertEqual(selected_date_order(self.bundle), "month_first")
        chosen = [o for o in date_order_preview(self.bundle) if o["value"] == "month_first"]
        self.assertTrue(chosen[0]["selected"])

    def test_choosing_a_date_order_leaves_the_name_order_untouched(self):
        """Both preferences share one JSON blob; neither may clobber the other."""
        self.bundle.mapping_summary = {
            "transform_prefs": {"name_order": "last_first", "date_order": "month_first"}
        }
        self.bundle.save(update_fields=["mapping_summary"])
        self.bundle.refresh_from_db()
        from apps.migration_cloud.views_tenant_upload import selected_name_order

        self.assertEqual(selected_name_order(self.bundle), "last_first")
        self.assertEqual(selected_date_order(self.bundle), "month_first")
