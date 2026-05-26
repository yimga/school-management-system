"""Wave S-C (v3.96.1 — 2026-05-26) — Behavior incidents + recognition tests."""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

from django.test import SimpleTestCase

from apps.student360.behavior_kernel import (
    append_behavior_event_to_settings,
    check_escalation,
    compute_house_totals,
    compute_student_point_total,
    get_category,
    list_negative_categories,
    list_positive_categories,
    record_behavior_event,
)


class CategoryRegistryTests(SimpleTestCase):

    def test_positive_categories_present(self):
        keys = {c.key for c in list_positive_categories()}
        for k in ("respect", "effort", "citizenship", "kindness", "leadership"):
            self.assertIn(k, keys)

    def test_negative_categories_present(self):
        keys = {c.key for c in list_negative_categories()}
        for k in (
            "tardiness", "disruption", "academic_dishonesty",
            "bullying", "uniform_violation", "missed_assignment",
        ):
            self.assertIn(k, keys)

    def test_severe_has_minus_5(self):
        bullying = get_category("bullying")
        self.assertEqual(bullying.severity, "severe")
        self.assertEqual(bullying.default_points, -5)


class RecordBehaviorEventTests(SimpleTestCase):

    def test_positive_records_correctly(self):
        event, audit = record_behavior_event(
            school_id=1, student_id=42, reporter_user_id=7,
            category_key="kindness", note="Helped a peer",
        )
        self.assertEqual(event.polarity, "positive")
        self.assertEqual(event.points, 2)
        self.assertEqual(audit.action, "CREATE")
        self.assertEqual(audit.sensitivity, "MEDIUM")

    def test_severe_bumps_audit_sensitivity(self):
        event, audit = record_behavior_event(
            school_id=1, student_id=42, reporter_user_id=7,
            category_key="bullying",
        )
        self.assertEqual(audit.sensitivity, "HIGH")

    def test_unknown_category_rejected(self):
        with self.assertRaises(ValueError):
            record_behavior_event(
                school_id=1, student_id=42, reporter_user_id=7,
                category_key="invented",
            )

    def test_points_override(self):
        event, _ = record_behavior_event(
            school_id=1, student_id=42, reporter_user_id=7,
            category_key="effort", points_override=5,
        )
        self.assertEqual(event.points, 5)


class StudentTotalTests(SimpleTestCase):

    def test_sums_positive_and_negative(self):
        e1, _ = record_behavior_event(
            school_id=1, student_id=42, reporter_user_id=7,
            category_key="kindness",
        )
        e2, _ = record_behavior_event(
            school_id=1, student_id=42, reporter_user_id=7,
            category_key="tardiness",
        )
        e3, _ = record_behavior_event(
            school_id=1, student_id=99, reporter_user_id=7,
            category_key="kindness",
        )
        total = compute_student_point_total(events=[e1, e2, e3], student_id=42)
        self.assertEqual(total, 2 + (-1))  # kindness=+2, tardiness=-1

    def test_returns_zero_for_unknown_student(self):
        self.assertEqual(
            compute_student_point_total(events=[], student_id=42), 0,
        )


class HouseTotalTests(SimpleTestCase):

    def test_aggregates_by_house(self):
        e1, _ = record_behavior_event(
            school_id=1, student_id=1, reporter_user_id=7,
            category_key="leadership", house_key="ruby",
        )
        e2, _ = record_behavior_event(
            school_id=1, student_id=2, reporter_user_id=7,
            category_key="kindness", house_key="ruby",
        )
        e3, _ = record_behavior_event(
            school_id=1, student_id=3, reporter_user_id=7,
            category_key="effort", house_key="emerald",
        )
        totals = compute_house_totals(events=[e1, e2, e3])
        self.assertEqual(totals["ruby"], 3 + 2)
        self.assertEqual(totals["emerald"], 1)

    def test_skips_houseless_events(self):
        e, _ = record_behavior_event(
            school_id=1, student_id=1, reporter_user_id=7,
            category_key="leadership",
        )
        totals = compute_house_totals(events=[e])
        self.assertEqual(totals, {})


class EscalationTests(SimpleTestCase):

    def _event(self, days_ago: int, category: str, student_id: int = 42):
        when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        event, _ = record_behavior_event(
            school_id=1, student_id=student_id, reporter_user_id=7,
            category_key=category, occurred_at_iso=when,
        )
        return event

    def test_none_for_clean_record(self):
        out = check_escalation(
            student_id=42, events=[
                self._event(2, "kindness"),
            ],
            today=date.today(),
        )
        self.assertIsNone(out)

    def test_severe_in_window_triggers_dsl_review(self):
        out = check_escalation(
            student_id=42, events=[self._event(5, "bullying")],
            today=date.today(),
        )
        self.assertIsNotNone(out)
        self.assertEqual(out.severity_label, "dsl_review")

    def test_three_moderate_in_window_counsellor_meeting(self):
        out = check_escalation(
            student_id=42, events=[
                self._event(1, "disruption"),
                self._event(5, "peer_conflict"),
                self._event(20, "property_misuse"),
            ],
            today=date.today(),
        )
        self.assertIsNotNone(out)
        self.assertEqual(out.severity_label, "counsellor_meeting")
        self.assertEqual(out.moderate_in_window, 3)

    def test_outside_window_ignored(self):
        out = check_escalation(
            student_id=42, events=[
                self._event(45, "disruption"),
                self._event(50, "disruption"),
                self._event(60, "disruption"),
            ],
            today=date.today(),
            window_days=30,
        )
        self.assertIsNone(out)

    def test_single_moderate_yields_notice(self):
        out = check_escalation(
            student_id=42, events=[self._event(2, "disruption")],
            today=date.today(),
        )
        self.assertIsNotNone(out)
        self.assertEqual(out.severity_label, "notice")


class StorageTests(SimpleTestCase):

    def test_append_fifo(self):
        event, _ = record_behavior_event(
            school_id=1, student_id=1, reporter_user_id=7,
            category_key="kindness",
        )
        out = append_behavior_event_to_settings(
            school_settings=None, event=event,
        )
        self.assertEqual(len(out["behavior"]["events"]), 1)
