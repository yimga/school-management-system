"""A name splitter must never empty an already-split column.

The best-formed CSV a school can send is ``first_name,last_name`` with one word
in each. The mapper attaches ``name_split_locale`` to every name-component
field unconditionally, so ``last_name = "Hopper"`` was split as if it were a
full name: ``_split_first_last("Hopper")`` yields ``("Hopper", "", "")``, and
``_pick`` -- asked for the ``last`` component because the canonical field is
``last_name`` -- returned the empty string.

Every student in that file then failed the lander's ``first/last`` requirement
and the whole roster was quarantined. Zero rows landed from a perfectly valid
import.

This was invisible for two reasons, both now closed: the bundle reported APPLIED
because rejecting every row was treated as a partial success, and the pipeline
test asserted only the bundle's status, never that a single student existed. It
surfaced the moment total rejection stopped reporting green.

The rule pinned here is deliberately absolute: a transformer may reshape a value,
never destroy it. A single token cannot be split, and it IS the component being
asked for.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.migration_cloud.transformers.base import TransformerContext, get_transformer


def _split(value: str, canonical_field: str, **options) -> str:
    tf = get_transformer("name_split_locale")
    ctx = TransformerContext(
        canonical_field=canonical_field, hints={}, options=options or {}
    )
    return tf.transform(value, ctx)


class SingleTokenNamesSurviveTests(SimpleTestCase):
    def test_a_one_word_last_name_is_not_erased(self):
        """The defect, exactly: Hopper in a last_name column became empty."""
        self.assertEqual(
            _split("Hopper", "last_name"),
            "Hopper",
            "a one-word surname was destroyed by the name splitter",
        )

    def test_a_one_word_first_name_survives(self):
        self.assertEqual(_split("Grace", "first_name"), "Grace")

    def test_a_real_combined_name_still_splits(self):
        self.assertEqual(_split("Grace Hopper", "first_name"), "Grace")
        self.assertEqual(_split("Grace Hopper", "last_name"), "Hopper")

    def test_a_one_word_value_has_no_middle_name(self):
        """A single token genuinely has no middle name — "" is correct here."""
        self.assertEqual(_split("Hopper", "middle_name"), "")

    def test_an_explicit_component_option_is_still_honoured(self):
        self.assertEqual(_split("Grace Hopper", "anything", component="last"), "Hopper")

    def test_a_full_name_target_is_unchanged(self):
        self.assertEqual(_split("Grace Hopper", "full_name"), "Grace Hopper")


class MapperDoesNotSplitAtomicColumnsTests(TestCase):
    """Belt and braces: do not attach a splitter where there is nothing to split."""

    def test_no_splitter_for_a_column_whose_values_are_single_words(self):
        from apps.migration_cloud.mapper import _suggest_transformer

        cf = {"canonical_field": "last_name", "value_type": "string", "domain": "students"}
        self.assertIsNone(
            _suggest_transformer(cf, "string", ["Hopper", "Lovelace", "Ngono"]),
            "a column of single-word surnames does not need a name splitter",
        )

    def test_splitter_still_attached_where_values_are_combined(self):
        from apps.migration_cloud.mapper import _suggest_transformer

        cf = {"canonical_field": "last_name", "value_type": "string", "domain": "students"}
        self.assertEqual(
            _suggest_transformer(cf, "string", ["Grace Hopper", "Ada Lovelace"]),
            "name_split_locale",
        )

    def test_splitter_attached_when_there_are_no_samples_to_judge_by(self):
        """With no evidence, keep the existing behaviour rather than guessing."""
        from apps.migration_cloud.mapper import _suggest_transformer

        cf = {"canonical_field": "last_name", "value_type": "string", "domain": "students"}
        self.assertEqual(_suggest_transformer(cf, "string", []), "name_split_locale")


class RosterLandsEndToEndTests(TestCase):
    """The whole point: a plain first/last roster must actually import."""

    def test_a_first_last_roster_lands_every_student(self):
        from apps.migration_cloud.landers.base import LanderContext
        from apps.migration_cloud.landers.student_lander import StudentLander
        from apps.people.models import StudentProfile
        from apps.schools.models import School

        school = School.objects.create(
            name="Roster School",
            slug="roster-school",
            subdomain="roster-school",
            is_active=True,
        )
        ctx = LanderContext(
            school=school, schema_name="", bundle_id=1, artifact_id=1, dry_run=False
        )
        rows = [
            {"external_id": "PS-100", "first_name": "Grace", "last_name": "Hopper"},
            {"external_id": "PS-101", "first_name": "Ada", "last_name": "Lovelace"},
        ]
        result = StudentLander().land(canonical_rows=iter(rows), ctx=ctx)
        self.assertEqual(result.quarantined, 0, result.errors)
        self.assertEqual(StudentProfile.objects.filter(school=school).count(), 2)
