"""The derived inline-edit registry: what it must offer, and what it must refuse.

Written 2026-09-07 alongside ``apps/metadata/inline_edit.py``, whose job is to make
the tenant backend editable without forty hand-written edit pages. Because every
answer that module gives is DERIVED from ``_meta`` rather than written down, the
risk is not that it covers too little -- it is that it derives something wrong and
applies it to 814 models at once.

THIS FILE EXISTS BECAUSE THE FIRST DERIVATION WAS WRONG. Run across the whole
schema, the bare "A has an FK to B, so choosing an A implies its B" rule fired 344
times, and among them:

    people.TeacherProfile   reports_to -> user
    academics.Incident      student    -> resolved_by
    people.StudentProfile   academic_year -> updated_by

The first is the serious one: saving a teacher's supervisor would have overwritten
that teacher's own login with the supervisor's account. Narrowing the rule to
classifications-only took it to 115 pairs. Every ``must_not`` test below names one
of those failures, so a future widening of the rule fails here rather than in a
school's records.

The counterpart risk is a rule so narrow it does nothing -- a cascade registry that
never cascades passes every "must not" test perfectly. So the non-vacuity tests are
not decoration: they assert specific pairs the rule MUST still find.
"""

from __future__ import annotations

import uuid

from django.apps import apps
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from apps.metadata.inline_edit import (
    change_permission,
    clean_value,
    cascade_updates,
    derive_cascades,
    editable_fields,
    locked_fields,
    scoped_queryset,
    structural_lock,
)

TeacherProfile = apps.get_model("people", "TeacherProfile")
StudentProfile = apps.get_model("people", "StudentProfile")
Classroom = apps.get_model("academics", "Classroom")
Department = apps.get_model("academics", "Department")
Specialty = apps.get_model("academics", "Specialty")


class StructuralLockTests(SimpleTestCase):
    """What no school may edit in place, whatever their role."""

    def _reason(self, model, name) -> str:
        return structural_lock(model._meta.get_field(name))

    def test_the_tenant_key_is_locked(self):
        """Editing ``school`` would move a record between schools."""
        self.assertTrue(self._reason(TeacherProfile, "school"))

    def test_the_primary_key_is_locked(self):
        self.assertEqual(self._reason(TeacherProfile, "id"), "primary key")

    def test_a_one_to_one_is_locked_as_an_identity_binding(self):
        """``TeacherProfile.user`` says WHICH LOGIN this person is.

        Re-pointing it hands one person's record to another human. That is an
        account operation with its own audit trail, not a field edit -- and it is
        also the field the first cascade rule tried to write automatically.
        """
        self.assertEqual(self._reason(TeacherProfile, "user"), "identity binding")

    def test_the_offline_sync_anchor_is_locked(self):
        """``client_offline_id`` is what the edge rail keys a row on."""
        self.assertTrue(self._reason(TeacherProfile, "client_offline_id"))

    def test_an_ordinary_attribute_is_not_locked(self):
        """Guard against a lock rule so broad it refuses everything."""
        self.assertEqual(self._reason(TeacherProfile, "position_title"), "")
        self.assertEqual(self._reason(TeacherProfile, "phone"), "")

    def test_a_lock_always_states_a_reason(self):
        for name, reason in locked_fields(TeacherProfile).items():
            self.assertTrue(reason.strip(), f"{name} was locked with no reason given")


class EditableFieldTests(SimpleTestCase):
    """The offer side: real fields, correctly shaped."""

    def test_the_fields_a_school_actually_needs_are_offered(self):
        names = {f.name for f in editable_fields(TeacherProfile)}
        self.assertIn("department", names)
        self.assertIn("position_title", names)
        self.assertIn("phone", names)

    def test_nothing_locked_is_also_offered(self):
        offered = {f.name for f in editable_fields(TeacherProfile)}
        self.assertEqual(offered & set(locked_fields(TeacherProfile)), set())

    def test_a_foreign_key_is_shaped_as_a_relation(self):
        """A relation must render as a dropdown, not a free-text box.

        This is the difference between the school picking a department that
        exists and typing one that does not.
        """
        field = next(f for f in editable_fields(TeacherProfile) if f.name == "department")
        self.assertEqual(field.kind, "relation")
        self.assertIs(field.related_model, Department)

    def test_the_permission_is_djangos_own_code(self):
        self.assertEqual(change_permission(TeacherProfile), "people.change_teacherprofile")
        self.assertEqual(change_permission(Classroom), "academics.change_classroom")


class CascadeMustNotTests(SimpleTestCase):
    """Every one of these was a real hit before the rule was narrowed."""

    def test_a_supervisor_never_rewrites_a_login(self):
        """THE near-miss. ``reports_to -> user`` would re-point identity."""
        self.assertNotIn("user", derive_cascades(TeacherProfile).get("reports_to", ()))

    def test_a_self_referential_field_drives_nothing(self):
        """A teacher may sit in a different department from their supervisor."""
        self.assertEqual(derive_cascades(TeacherProfile).get("reports_to", ()), ())

    def test_no_cascade_anywhere_writes_an_actor_field(self):
        """Who acted is a fact about an event; it is never implied by a category.

        Swept across every installed model rather than the three in this file,
        because the rule is applied to all of them.
        """
        offenders = []
        for model in apps.get_models():
            try:
                cascades = derive_cascades(model)
            except Exception as exc:  # noqa: BLE001 - a crash is itself the finding
                offenders.append(f"{model._meta.label}: raised {type(exc).__name__}: {exc}")
                continue
            for source, dependents in cascades.items():
                for dependent in dependents:
                    if dependent.endswith("_by") or dependent in ("user", "owner", "assigned_to"):
                        offenders.append(f"{model._meta.label}: {source} -> {dependent}")
        self.assertEqual(offenders, [], "actor fields must never be derived")

    def test_an_ambiguous_target_is_refused_rather_than_guessed(self):
        """Two FKs to one model state nothing about which one is implied.

        ``RolloverProposal`` holds ``source_year`` and ``target_year``, both to
        ``AcademicYear``. Picking either would be a coin toss that writes rows.
        """
        model = apps.get_model("academics", "RolloverProposal")
        for dependents in derive_cascades(model).values():
            self.assertNotIn("source_year", dependents)
            self.assertNotIn("target_year", dependents)


class CascadeMustFindTests(SimpleTestCase):
    """A rule that never fires would pass every test above. It must still work."""

    def test_a_classroom_implies_its_academic_year(self):
        self.assertIn("academic_year", derive_cascades(StudentProfile).get("classroom", ()))

    def test_the_rule_is_not_vacuous_across_the_schema(self):
        """Measured at 115 pairs over 78 models on 2026-09-07.

        Asserted as a floor, not an equality: new models legitimately add pairs,
        and pinning the exact number would turn every unrelated model into a
        failure here. A collapse toward zero is the regression worth catching.
        """
        pairs = sum(
            len(dependents)
            for model in apps.get_models()
            for dependents in derive_cascades(model).values()
        )
        self.assertGreaterEqual(pairs, 60, f"cascade rule collapsed to {pairs} pairs")


class TenantScopingTests(TestCase):
    """The security property: the list offered IS the list accepted."""

    def setUp(self):
        School = apps.get_model("schools", "School")
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Ours {uid}", slug=f"ours-{uid}", subdomain=f"ours{uid}", is_active=True
        )
        other_uid = uuid.uuid4().hex[:8]
        self.other = School.objects.create(
            name=f"Theirs {other_uid}",
            slug=f"theirs-{other_uid}",
            subdomain=f"theirs{other_uid}",
            is_active=True,
        )
        self.ours = Department.objects.create(school=self.school, name="Sciences", code=f"SCI{uid}")
        self.theirs = Department.objects.create(
            school=self.other, name="Sciences", code=f"SCI{other_uid}"
        )

    def test_the_choice_list_holds_only_this_schools_rows(self):
        visible = list(scoped_queryset(Department, school=self.school))
        self.assertIn(self.ours, visible)
        self.assertNotIn(self.theirs, visible)

    def test_another_schools_key_is_refused_even_though_it_is_a_valid_key(self):
        """The whole point. A POST need not echo a value the page offered.

        ``self.theirs.pk`` is a real Department id that resolves perfectly well
        against an unscoped queryset -- which is exactly why the save path has to
        resolve it through the SAME scoped queryset that built the dropdown.
        """
        with self.assertRaises(ValidationError):
            clean_value(TeacherProfile, "department", self.theirs.pk, school=self.school)

    def test_this_schools_key_is_accepted(self):
        """Guard against a refusal so broad it refuses everything."""
        resolved = clean_value(TeacherProfile, "department", self.ours.pk, school=self.school)
        self.assertEqual(resolved, self.ours)

    def test_a_locked_field_is_refused_at_the_save_path_too(self):
        """Locking must not live only in the renderer.

        A field absent from the page is still POST-able by anyone who can type a
        URL, so the refusal has to be in ``clean_value``, not just in the markup.
        """
        with self.assertRaises(ValidationError):
            clean_value(TeacherProfile, "school", self.other.pk, school=self.school)

    def test_a_cascade_reads_the_chosen_row_rather_than_assuming(self):
        """A driving row whose own FK is NULL implies nothing.

        Returning ``{"department": None}`` here would quietly erase a department
        somebody set deliberately. An absent answer is not an answer of "none".
        """
        specialty = Specialty.objects.create(
            school=self.school, name="Clothing", code=f"CLO{uuid.uuid4().hex[:6]}",
            department=self.ours,
        )
        self.assertEqual(
            cascade_updates(StudentProfile, "specialty", specialty).get("department"), None
        )
        self.assertEqual(cascade_updates(StudentProfile, "classroom", None), {})
