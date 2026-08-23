"""A platform-wide (school=None) DynamicFieldDefinition must not fork per school.

``seed_platform_eav_baseline()`` ships definitions with ``school=None``. When a
tenant admin saves a value for one of them, ``set_dynamic_field_value`` used to
``get_or_create(school=<S>)``, which never matched the null-school row and so
created a SECOND definition for the same (entity_type, field_key) — after which
``definitions_for_entity`` returned both and the field rendered twice on the
student detail page and the report card.
"""

from __future__ import annotations

from django.test import TestCase

from apps.metadata.dynamic_forms import (
    definitions_for_entity,
    dynamic_field_display_rows,
)
from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
from apps.metadata.services import get_dynamic_field_value, set_dynamic_field_value
from apps.people.models import StudentProfile
from apps.schools.models import School

ENTITY = "people.studentprofile"


class PlatformDefinitionNoForkTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Fork Guard School",
            slug="fork-guard-school",
            subdomain="fork-guard-school",
            country_code="CM",
        )
        self.student = StudentProfile.objects.create(
            first_name="Ada",
            last_name="Nkeng",
            school=self.school,
        )
        # The platform-wide baseline row: school=None, human-authored label.
        self.platform_defn = DynamicFieldDefinition.objects.create(
            entity_type=ENTITY,
            field_key="preferred_pronouns",
            school=None,
            label="Preferred pronouns",
            data_type="string",
            is_active=True,
        )

    def test_saving_a_value_does_not_fork_the_platform_definition(self):
        set_dynamic_field_value(
            self.student, "preferred_pronouns", "they/them", school=self.school
        )
        # Vacuity guard: the call actually reached the write path.
        self.assertTrue(
            DynamicFieldValue.objects.filter(
                school=self.school,
                entity_type=ENTITY,
                entity_id=str(self.student.pk),
                field_key="preferred_pronouns",
            ).exists(),
            "set_dynamic_field_value did not persist a value — the test would "
            "pass vacuously against a no-op call path",
        )
        self.assertEqual(
            get_dynamic_field_value(
                self.student, "preferred_pronouns", school=self.school
            ),
            "they/them",
        )
        defns = DynamicFieldDefinition.objects.filter(
            entity_type=ENTITY, field_key="preferred_pronouns"
        )
        self.assertEqual(
            [d.school_id for d in defns.order_by("id")],
            [None],
            "the platform-wide definition was forked into a per-school duplicate",
        )

    def test_detail_rows_render_the_field_once(self):
        set_dynamic_field_value(
            self.student, "preferred_pronouns", "they/them", school=self.school
        )
        rows = dynamic_field_display_rows(
            self.student, school=self.school, entity_type=ENTITY
        )
        pronoun_rows = [r for r in rows if r["value"] == "they/them"]
        # Vacuity guard: the row must be present at all, not merely non-duplicated.
        self.assertEqual(
            len(pronoun_rows), 1, f"custom field rendered {len(pronoun_rows)} times: {rows}"
        )
        self.assertEqual(pronoun_rows[0]["label"], "Preferred pronouns")

    def test_school_override_wins_and_collapses_the_platform_row(self):
        """A deliberate per-school override must replace, not double, the baseline."""
        DynamicFieldDefinition.objects.create(
            entity_type=ENTITY,
            field_key="preferred_pronouns",
            school=self.school,
            label="Pronouns (school wording)",
            data_type="string",
            is_active=True,
            required=True,
        )
        defns = definitions_for_entity(school=self.school, entity_type=ENTITY)
        keys = [d.field_key for d in defns]
        self.assertEqual(
            keys.count("preferred_pronouns"),
            1,
            f"definitions_for_entity returned duplicates for one field_key: {keys}",
        )
        winner = next(d for d in defns if d.field_key == "preferred_pronouns")
        self.assertEqual(winner.school_id, self.school.pk)
        self.assertEqual(winner.label, "Pronouns (school wording)")
        self.assertTrue(winner.required)

    def test_platform_row_still_visible_when_no_override_exists(self):
        """Vacuity guard on the dedupe: it must not drop null-school rows."""
        defns = definitions_for_entity(school=self.school, entity_type=ENTITY)
        keys = [d.field_key for d in defns]
        self.assertIn("preferred_pronouns", keys)
        winner = next(d for d in defns if d.field_key == "preferred_pronouns")
        self.assertIsNone(winner.school_id)
