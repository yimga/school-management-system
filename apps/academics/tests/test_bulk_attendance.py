"""Wave R-A (v3.96.0 — 2026-05-26) — Bulk attendance kernel tests."""

from __future__ import annotations

from datetime import date

from django.test import SimpleTestCase

from apps.academics.bulk_attendance import (
    AttendanceRow,
    BulkAttendanceResult,
    apply_attendance_rows,
    mark_whole_class,
    normalize_status,
    parse_attendance_csv,
)


class NormalizeStatusTests(SimpleTestCase):

    def test_accepts_lowercase(self):
        self.assertEqual(normalize_status("present"), "present")
        self.assertEqual(normalize_status("absent"), "absent")
        self.assertEqual(normalize_status("late"), "late")
        self.assertEqual(normalize_status("excused"), "excused")

    def test_accepts_mixed_case(self):
        self.assertEqual(normalize_status("Present"), "present")
        self.assertEqual(normalize_status("  ABSENT  "), "absent")

    def test_rejects_unknown(self):
        with self.assertRaises(ValueError):
            normalize_status("tardy")


class ParseAttendanceCSVTests(SimpleTestCase):

    def test_minimal_csv(self):
        text = "student_external_id,status\nSTU-1,present\nSTU-2,absent\n"
        rows = parse_attendance_csv(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].student_external_id, "STU-1")
        self.assertEqual(rows[0].status, "present")
        self.assertEqual(rows[1].status, "absent")

    def test_with_remarks(self):
        text = (
            "student_external_id,status,remarks\n"
            "STU-1,late,bus delay\n"
        )
        rows = parse_attendance_csv(text)
        self.assertEqual(rows[0].remarks, "bus delay")

    def test_header_capitalisation_tolerant(self):
        text = "Student_External_Id,Status\nSTU-1,Present\n"
        rows = parse_attendance_csv(text)
        self.assertEqual(rows[0].student_external_id, "STU-1")
        self.assertEqual(rows[0].status, "present")

    def test_missing_required_columns_raises(self):
        text = "student_external_id\nSTU-1\n"
        with self.assertRaises(ValueError):
            parse_attendance_csv(text)

    def test_skips_blank_ids(self):
        text = "student_external_id,status\n,present\nSTU-1,absent\n"
        rows = parse_attendance_csv(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].student_external_id, "STU-1")

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(parse_attendance_csv(""), [])


class MarkWholeClassRunnerTests(SimpleTestCase):
    """Use an injected runner so we don't touch the DB."""

    def test_default_status_propagates_to_runner(self):
        captured = {}

        def fake_runner(**kw):
            captured.update(kw)
            return BulkAttendanceResult(created=3, student_count=3)

        result = mark_whole_class(
            classroom_id=7,
            date_value=date(2026, 5, 26),
            default_status="present",
            school_id=1,
            db_runner=fake_runner,
        )
        self.assertEqual(result.created, 3)
        self.assertEqual(captured["default_status"], "present")
        self.assertEqual(captured["classroom_id"], 7)
        self.assertEqual(captured["school_id"], 1)
        self.assertEqual(captured["exceptions"], {})

    def test_exceptions_normalize(self):
        captured = {}

        def fake_runner(**kw):
            captured.update(kw)
            return BulkAttendanceResult()

        mark_whole_class(
            classroom_id=7,
            date_value=date(2026, 5, 26),
            default_status="present",
            exceptions={17: "Absent", 18: "LATE"},
            school_id=1,
            db_runner=fake_runner,
        )
        self.assertEqual(captured["exceptions"], {17: "absent", 18: "late"})

    def test_unknown_status_rejected_eagerly(self):
        def never_called(**kw):
            self.fail("runner should not be called when status invalid")

        with self.assertRaises(ValueError):
            mark_whole_class(
                classroom_id=7,
                date_value=date(2026, 5, 26),
                default_status="tardy",
                school_id=1,
                db_runner=never_called,
            )


class ApplyAttendanceRowsRunnerTests(SimpleTestCase):

    def test_rows_passed_through(self):
        captured = {}

        def fake_runner(**kw):
            captured.update(kw)
            return BulkAttendanceResult(created=2, student_count=2)

        rows = [
            AttendanceRow(student_external_id="STU-1", status="present"),
            AttendanceRow(student_external_id="STU-2", status="absent", remarks="sick"),
        ]
        result = apply_attendance_rows(
            classroom_id=7,
            date_value=date(2026, 5, 26),
            rows=rows,
            school_id=1,
            db_runner=fake_runner,
        )
        self.assertEqual(result.created, 2)
        self.assertEqual(len(captured["rows"]), 2)
        self.assertEqual(captured["rows"][1].remarks, "sick")
        self.assertEqual(captured["school_id"], 1)


class BulkAttendanceResultTests(SimpleTestCase):

    def test_as_dict_shape(self):
        r = BulkAttendanceResult(created=1, updated=2, skipped=3, student_count=6)
        r.errors.append({"student_external_id": "X", "reason": "not_in_classroom"})
        d = r.as_dict()
        self.assertEqual(d["created"], 1)
        self.assertEqual(d["updated"], 2)
        self.assertEqual(d["skipped"], 3)
        self.assertEqual(d["student_count"], 6)
        self.assertEqual(len(d["errors"]), 1)
