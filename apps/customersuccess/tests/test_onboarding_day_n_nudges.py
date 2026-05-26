"""Wave R-E (v3.96.0 — 2026-05-26) — Onboarding nudge kernel tests."""

from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase

from apps.customersuccess.onboarding_day_n_nudges import (
    compute_due_nudges,
    get_onboarding_task,
    get_sent_markers,
    list_onboarding_tasks,
    record_nudge_sent,
)


class TaskRegistryTests(SimpleTestCase):

    def test_at_least_seven_tasks(self):
        self.assertGreaterEqual(len(list_onboarding_tasks()), 7)

    def test_known_keys_present(self):
        for key in (
            "import_students", "configure_branding", "invite_teachers",
            "set_up_fees", "first_announcement", "calendar_setup",
            "complete_setup_studio",
        ):
            self.assertIsNotNone(get_onboarding_task(key))


class ComputeDueNudgesTests(SimpleTestCase):

    def test_negative_days_returns_empty(self):
        batch = compute_due_nudges(
            school_id=1,
            signup_date=date(2026, 6, 1),
            today=date(2026, 5, 26),
            completed_task_keys=None,
            already_sent_markers=None,
        )
        self.assertEqual(batch.due, [])

    def test_day_2_emits_two_day_nudges(self):
        batch = compute_due_nudges(
            school_id=1,
            signup_date=date(2026, 5, 24),
            today=date(2026, 5, 26),
            completed_task_keys=set(),
            already_sent_markers=set(),
        )
        keys = {d.task_key for d in batch.due}
        # 2-day nudges: import_students, invite_teachers, calendar_setup.
        self.assertIn("import_students", keys)
        self.assertIn("invite_teachers", keys)

    def test_completed_task_skipped(self):
        batch = compute_due_nudges(
            school_id=1,
            signup_date=date(2026, 5, 24),
            today=date(2026, 5, 26),
            completed_task_keys={"import_students"},
            already_sent_markers=set(),
        )
        keys = {d.task_key for d in batch.due}
        self.assertNotIn("import_students", keys)

    def test_already_sent_not_resent(self):
        batch = compute_due_nudges(
            school_id=1,
            signup_date=date(2026, 5, 24),
            today=date(2026, 5, 26),
            completed_task_keys=set(),
            already_sent_markers={"import_students:2"},
        )
        keys = {d.task_key for d in batch.due}
        # Already sent — should NOT re-emit even though day 2 has passed.
        self.assertNotIn("import_students", keys)

    def test_only_highest_overdue_offset_per_task(self):
        # 21 days in — import_students has offsets (2, 5, 10, 21).
        # Schedule should emit ONLY the 21-day variant, not all four.
        batch = compute_due_nudges(
            school_id=1,
            signup_date=date(2026, 5, 5),
            today=date(2026, 5, 26),
            completed_task_keys=set(),
            already_sent_markers=set(),
        )
        import_nudges = [d for d in batch.due if d.task_key == "import_students"]
        self.assertEqual(len(import_nudges), 1)
        self.assertEqual(import_nudges[0].day_offset, 21)

    def test_day_offsets_sorted_in_batch(self):
        batch = compute_due_nudges(
            school_id=1,
            signup_date=date(2026, 5, 19),
            today=date(2026, 5, 26),
            completed_task_keys=set(),
            already_sent_markers=set(),
        )
        offsets = [d.day_offset for d in batch.due]
        self.assertEqual(offsets, sorted(offsets))

    def test_markers_include_day_offset(self):
        batch = compute_due_nudges(
            school_id=1,
            signup_date=date(2026, 5, 24),
            today=date(2026, 5, 26),
            completed_task_keys=set(),
            already_sent_markers=set(),
        )
        for d in batch.due:
            self.assertIn(":", d.marker)
            task_key, offset_str = d.marker.split(":")
            self.assertEqual(task_key, d.task_key)
            self.assertEqual(int(offset_str), d.day_offset)


class RecordNudgeSentTests(SimpleTestCase):

    def test_appends_marker(self):
        out = record_nudge_sent(school_settings=None, marker="import_students:2")
        self.assertIn("import_students:2", get_sent_markers(out))

    def test_dedup(self):
        s = record_nudge_sent(school_settings={}, marker="a:1")
        s = record_nudge_sent(school_settings=s, marker="a:1")
        self.assertEqual(len(s["customersuccess"]["nudges_sent"]), 1)

    def test_fifo_cap(self):
        s = {}
        for i in range(250):
            s = record_nudge_sent(school_settings=s, marker=f"x:{i}", cap=200)
        sent = s["customersuccess"]["nudges_sent"]
        self.assertEqual(len(sent), 200)
        # Oldest dropped first.
        self.assertNotIn("x:0", sent)
        self.assertIn("x:249", sent)

    def test_preserves_unrelated_keys(self):
        seed = {"customersuccess": {"other_state": True}}
        out = record_nudge_sent(school_settings=seed, marker="m:1")
        self.assertTrue(out["customersuccess"]["other_state"])
