"""The operator chooses how combined names split, previews it, and it is honoured.

Name splitting was automatic and invisible: a roster written surname-first had the
family name read as the given name for every student in the file, with no way to
say otherwise and no way to see the result before committing. "ANDONGMAD FAVOUR
ANGU" is only ambiguous until you see which way each option reads it, so the
preview is built from the school's OWN profiled samples rather than invented
examples.

The choice rides ``mapping_summary['transform_prefs']`` -- the JSON the
orchestrator already reads -- and reaches every person lander through
``LanderContext.transformer_options``, which the dataclass has always declared and
nothing ever populated. No new model, no second source of truth.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.student_lander import StudentLander
from apps.migration_cloud.landers._helpers import resolve_name_order, split_name_for
from apps.migration_cloud.models import MigrationArtifact, MigrationBundle
from apps.migration_cloud.views_tenant_upload import (
    NAME_ORDER_CHOICES,
    TenantMigrationReviewView,
    name_order_preview,
    selected_name_order,
)
from apps.people.models import StudentProfile
from apps.schools.models import School


class NameOrderResolutionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Order School", slug="order-school", subdomain="order-school", is_active=True
        )

    def _ctx(self, **options):
        return LanderContext(
            school=self.school,
            schema_name="",
            bundle_id=1,
            artifact_id=1,
            dry_run=False,
            transformer_options=options,
        )

    def test_unset_preference_auto_detects(self):
        self.assertEqual(resolve_name_order(self._ctx()), "")

    def test_unknown_value_is_ignored_rather_than_trusted(self):
        self.assertEqual(resolve_name_order(self._ctx(name_order="nonsense")), "")

    def test_family_name_first_is_honoured(self):
        first, _middle, last = split_name_for(self._ctx(name_order="last_first"), "ANDONGMAD FAVOUR")
        self.assertEqual(first.upper(), "FAVOUR")
        self.assertEqual(last.upper(), "ANDONGMAD")

    def test_given_name_first_is_honoured(self):
        first, _middle, last = split_name_for(self._ctx(name_order="first_last"), "ANDONGMAD FAVOUR")
        self.assertEqual(first.upper(), "ANDONGMAD")
        self.assertEqual(last.upper(), "FAVOUR")

    def test_choice_changes_what_the_lander_actually_stores(self):
        """The end of the chain: preference -> context -> landed columns."""
        row = {"full_name": "ANDONGMAD FAVOUR", "date_of_birth": "2012-01-25"}
        StudentLander().land(
            canonical_rows=iter([dict(row)]), ctx=self._ctx(name_order="last_first")
        )
        student = StudentProfile.objects.get(school=self.school)
        self.assertEqual(student.first_name.upper(), "FAVOUR")
        self.assertEqual(student.last_name.upper(), "ANDONGMAD")


class NameOrderPreviewTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Preview School",
            slug="preview-school",
            subdomain="preview-school",
            is_active=True,
        )
        self.bundle = MigrationBundle.objects.create(school=self.school)
        MigrationArtifact.objects.create(
            bundle=self.bundle,
            path_within_bundle="students.xlsx",
            filename="students.xlsx",
            sha256="p" * 64,
            locale_hints={},
            profile={
                "columns": [
                    {
                        "name": "Full Name",
                        "normalized": "full_name",
                        "samples": ["ANDONGMAD FAVOUR ANGU", "AWA BERTRAND"],
                    }
                ]
            },
        )

    def test_preview_uses_the_schools_own_names(self):
        preview = name_order_preview(self.bundle)
        self.assertEqual(len(preview), len(NAME_ORDER_CHOICES))
        sources = {r["source"] for option in preview for r in option["rows"]}
        self.assertIn("ANDONGMAD FAVOUR ANGU", sources)

    def test_preview_shows_the_orders_differing(self):
        by_value = {o["value"]: o["rows"][0] for o in name_order_preview(self.bundle)}
        self.assertNotEqual(
            by_value["first_last"]["last"],
            by_value["last_first"]["last"],
            "the two orders previewed identically — the preview cannot inform a choice",
        )

    def test_program_name_columns_are_not_previewed_as_people(self):
        MigrationArtifact.objects.filter(bundle=self.bundle).update(
            assigned_domain="programs",
            profile={
                "columns": [
                    {
                        "name": "Name",
                        "normalized": "name",
                        "samples": ["ELECTRICAL POWER SYSTEMS", "FASHION DESIGN"],
                    }
                ]
            },
        )
        self.assertEqual(name_order_preview(self.bundle), [])

    def test_program_titles_are_skipped_even_on_a_student_sheet(self):
        """The live screenshot: a Name column of TVET titles, mis-typed as students."""
        MigrationArtifact.objects.filter(bundle=self.bundle).update(
            assigned_domain="students",
            filename="students.xlsx",
            path_within_bundle="students.xlsx",
            profile={
                "columns": [
                    {
                        "name": "Name",
                        "normalized": "name",
                        "samples": [
                            "ELECTRICAL POWER SYSTEMS",
                            "FASHION DESIGN",
                            "BUILDING CONSTRUCTION",
                            "CARPENTRY AND JOINERY",
                            "MOTOR MECHANICS",
                        ],
                    }
                ]
            },
        )
        self.assertEqual(name_order_preview(self.bundle), [])

    def test_trade_filename_is_not_previewed_as_people(self):
        artifact = MigrationArtifact.objects.get(bundle=self.bundle)
        artifact.filename = "trades.xlsx"
        artifact.path_within_bundle = "trades.xlsx"
        artifact.assigned_domain = "students"
        artifact.profile = {
            "columns": [
                {
                    "name": "Full Name",
                    "normalized": "full_name",
                    "samples": ["ELECTRICAL POWER SYSTEMS"],
                }
            ]
        }
        artifact.save()
        self.assertEqual(name_order_preview(self.bundle), [])

    def test_mapped_full_name_column_is_used_even_when_header_is_name(self):
        artifact = MigrationArtifact.objects.get(bundle=self.bundle)
        artifact.filename = "students.xlsx"
        artifact.path_within_bundle = "students.xlsx"
        artifact.assigned_domain = "students"
        artifact.profile = {
            "columns": [
                {
                    "name": "Name",
                    "normalized": "name",
                    "samples": ["ANDONGMAD FAVOUR ANGU"],
                }
            ]
        }
        artifact.save()
        self.bundle.mapping_summary = {
            "per_artifact": {
                "students.xlsx": [
                    {
                        "source_column": "Name",
                        "canonical_field": "full_name",
                        "confidence": 0.9,
                    }
                ]
            }
        }
        self.bundle.save(update_fields=["mapping_summary"])
        sources = {r["source"] for option in name_order_preview(self.bundle) for r in option["rows"]}
        self.assertIn("ANDONGMAD FAVOUR ANGU", sources)
        MigrationArtifact.objects.filter(bundle=self.bundle).update(
            profile={"columns": [{"name": "Score", "normalized": "score", "samples": ["12"]}]}
        )
        self.assertEqual(name_order_preview(self.bundle), [])

    def test_selection_round_trips_through_the_bundle(self):
        self.assertEqual(selected_name_order(self.bundle), "")
        self.bundle.mapping_summary = {"transform_prefs": {"name_order": "last_first"}}
        self.bundle.save(update_fields=["mapping_summary"])
        self.bundle.refresh_from_db()
        self.assertEqual(selected_name_order(self.bundle), "last_first")
        self.assertTrue(
            [o for o in name_order_preview(self.bundle) if o["value"] == "last_first"][0][
                "selected"
            ]
        )

    def test_review_post_persists_the_chosen_order(self):
        request = RequestFactory().post("/review/", {"name_order": "last_first"})
        changed = TenantMigrationReviewView()._apply_name_order(request, self.bundle)
        self.assertEqual(changed, 1)
        self.bundle.refresh_from_db()
        self.assertEqual(selected_name_order(self.bundle), "last_first")
        self.assertEqual(
            (self.bundle.mapping_summary or {}).get("transform_prefs", {}).get("name_order"),
            "last_first",
        )

    def test_transform_prefs_action_persists_without_file_fields(self):
        request = RequestFactory().post(
            "/review/",
            {"action": "save_transform_prefs", "name_order": "last_first"},
        )
        view = TenantMigrationReviewView()
        self.assertEqual(view._apply_name_order(request, self.bundle), 1)
        self.assertEqual(view._apply_column_overrides(request, self.bundle), 0)
        self.bundle.refresh_from_db()
        self.assertEqual(selected_name_order(self.bundle), "last_first")


class NameOrderSurfaceContractTests(SimpleTestCase):
    def test_review_template_does_not_clip_radios_in_a_responsive_table(self):
        html = (Path(settings.BASE_DIR) / "templates/migration_cloud/connector/bundle_review.html").read_text(
            encoding="utf-8"
        )
        css = (Path(settings.BASE_DIR) / "static/css/migration-cloud-ui.css").read_text(
            encoding="utf-8"
        )
        start = html.find("data-rmc-name-order")
        self.assertGreater(start, 0)
        block = html[start : html.find("</fieldset>", start)]
        self.assertIn('class="rmc-name-order__option"', block)
        self.assertIn('class="rmc-name-order__control"', block)
        self.assertNotIn("form-check", block)
        self.assertIn('data-rmc-transform-prefs-form="1"', html)
        self.assertIn('value="save_transform_prefs"', html)
        self.assertIn("Save name & date preferences", html)
        self.assertIn(".rmc-name-order__control > input[type=\"radio\"]", css)
        self.assertIn("appearance: none", css)
        self.assertIn("overflow: visible", css)
        self.assertIn("min-height: 44px", css)
        self.assertIn("opacity: 0", css)
        self.assertIn(".rmc-name-order__control::after", css)
