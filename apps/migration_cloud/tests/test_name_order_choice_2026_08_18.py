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

from django.test import TestCase

from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.student_lander import StudentLander
from apps.migration_cloud.landers._helpers import resolve_name_order, split_name_for
from apps.migration_cloud.models import MigrationArtifact, MigrationBundle
from apps.migration_cloud.views_tenant_upload import (
    NAME_ORDER_CHOICES,
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

    def test_preview_is_empty_when_there_is_no_combined_name_column(self):
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
