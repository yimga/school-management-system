"""Wave S-D (v3.96.1 — 2026-05-26) — Records-hold kernel tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.student360.records_hold_kernel import (
    ACTIVE,
    ESCALATED,
    RESOLVED,
    InvalidHoldTransition,
    active_holds_for_student,
    append_hold_to_settings,
    can_release_transcript,
    create_hold,
    get_category,
    list_categories,
    transition_hold,
)


class CategoryTests(SimpleTestCase):

    def test_six_categories_present(self):
        keys = {c.key for c in list_categories()}
        for k in (
            "financial", "disciplinary", "library", "academic",
            "counsel_review", "incomplete_paperwork",
        ):
            self.assertIn(k, keys)

    def test_financial_is_hard(self):
        self.assertEqual(get_category("financial").default_severity, "hard")

    def test_disciplinary_is_counsel_pending(self):
        self.assertTrue(get_category("disciplinary").counsel_pending)


class CreateHoldTests(SimpleTestCase):

    def test_happy_path_financial(self):
        h = create_hold(
            school_id=1, student_id=42, category_key="financial",
            reason="Outstanding fees $250.00", actor_user_id=7,
        )
        self.assertEqual(h.stage, ACTIVE)
        self.assertEqual(h.severity, "hard")

    def test_severity_override(self):
        h = create_hold(
            school_id=1, student_id=42, category_key="library",
            reason="Three overdue books", severity_override="hard",
        )
        self.assertEqual(h.severity, "hard")

    def test_unknown_category_rejected(self):
        with self.assertRaises(ValueError):
            create_hold(
                school_id=1, student_id=42, category_key="invented",
                reason="Some reason",
            )

    def test_short_reason_rejected(self):
        with self.assertRaises(ValueError):
            create_hold(
                school_id=1, student_id=42, category_key="financial",
                reason="x",
            )


class TransitionHoldTests(SimpleTestCase):

    def _seed(self):
        return create_hold(
            school_id=1, student_id=42, category_key="financial",
            reason="Outstanding fees $250.00", actor_user_id=7,
        )

    def test_active_to_resolved(self):
        h = self._seed()
        h2 = transition_hold(
            hold=h, target_stage=RESOLVED, actor_user_id=99,
            note="Parent paid in full",
        )
        self.assertEqual(h2.stage, RESOLVED)
        self.assertEqual(h2.resolved_by_user_id, 99)

    def test_resolved_is_terminal(self):
        h = self._seed()
        h = transition_hold(hold=h, target_stage=RESOLVED, actor_user_id=99)
        with self.assertRaises(InvalidHoldTransition):
            transition_hold(hold=h, target_stage=ACTIVE, actor_user_id=99)

    def test_escalated_can_un_escalate(self):
        h = self._seed()
        h = transition_hold(hold=h, target_stage=ESCALATED, actor_user_id=99)
        h = transition_hold(hold=h, target_stage=ACTIVE, actor_user_id=99)
        self.assertEqual(h.stage, ACTIVE)


class CanReleaseTranscriptTests(SimpleTestCase):

    def test_no_holds_can_release(self):
        d = can_release_transcript(student_id=42, holds=[])
        self.assertTrue(d.can_release)
        self.assertEqual(d.hard_blockers, [])

    def test_active_hard_hold_blocks(self):
        h = create_hold(
            school_id=1, student_id=42, category_key="financial",
            reason="Owed $250",
        )
        d = can_release_transcript(student_id=42, holds=[h])
        self.assertFalse(d.can_release)
        self.assertEqual(len(d.hard_blockers), 1)

    def test_soft_hold_warns_but_allows(self):
        h = create_hold(
            school_id=1, student_id=42, category_key="library",
            reason="Three books overdue",
        )
        d = can_release_transcript(student_id=42, holds=[h])
        self.assertTrue(d.can_release)
        self.assertEqual(len(d.soft_warnings), 1)

    def test_resolved_hold_does_not_block(self):
        h = create_hold(
            school_id=1, student_id=42, category_key="financial",
            reason="Owed $250",
        )
        h = transition_hold(hold=h, target_stage=RESOLVED, actor_user_id=7)
        d = can_release_transcript(student_id=42, holds=[h])
        self.assertTrue(d.can_release)

    def test_other_students_holds_ignored(self):
        other = create_hold(
            school_id=1, student_id=99, category_key="financial",
            reason="Other student",
        )
        d = can_release_transcript(student_id=42, holds=[other])
        self.assertTrue(d.can_release)

    def test_escalated_still_blocks(self):
        h = create_hold(
            school_id=1, student_id=42, category_key="financial",
            reason="Big balance",
        )
        h = transition_hold(hold=h, target_stage=ESCALATED, actor_user_id=7)
        d = can_release_transcript(student_id=42, holds=[h])
        self.assertFalse(d.can_release)


class StorageTests(SimpleTestCase):

    def test_append_and_lookup(self):
        h = create_hold(
            school_id=1, student_id=42, category_key="financial",
            reason="Big balance",
        )
        s = append_hold_to_settings(school_settings={}, hold=h)
        active = active_holds_for_student(school_settings=s, student_id=42)
        self.assertEqual(len(active), 1)

    def test_replace_by_hold_id(self):
        h = create_hold(
            school_id=1, student_id=42, category_key="financial",
            reason="Big balance",
        )
        s = append_hold_to_settings(school_settings={}, hold=h)
        h2 = transition_hold(hold=h, target_stage=ESCALATED, actor_user_id=7)
        s = append_hold_to_settings(school_settings=s, hold=h2)
        rows = s["records_holds"]["42"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stage"], ESCALATED)

    def test_resolved_excluded_from_active_lookup(self):
        h = create_hold(
            school_id=1, student_id=42, category_key="financial",
            reason="Big balance",
        )
        s = append_hold_to_settings(school_settings={}, hold=h)
        h = transition_hold(hold=h, target_stage=RESOLVED, actor_user_id=7)
        s = append_hold_to_settings(school_settings=s, hold=h)
        self.assertEqual(
            active_holds_for_student(school_settings=s, student_id=42), [],
        )
