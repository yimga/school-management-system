"""Tests for QR attendance pilot (batch 1534)."""

from __future__ import annotations

from datetime import date
from unittest import mock

from django.test import SimpleTestCase

from apps.academics.qr_attendance import (
    mint_student_attendance_token,
    parse_qr_token_lines,
    verify_student_attendance_token,
)


class QrAttendanceTokenTests(SimpleTestCase):
    def test_mint_and_verify_round_trip(self):
        token = mint_student_attendance_token(
            school_id=1,
            student_id=42,
            student_code="STU-001",
        )
        self.assertTrue(token.startswith("RMC-ATT-42-"))
        self.assertTrue(
            verify_student_attendance_token(
                token,
                school_id=1,
                student_id=42,
                student_code="STU-001",
            )
        )
        self.assertFalse(
            verify_student_attendance_token(
                token,
                school_id=1,
                student_id=42,
                student_code="STU-002",
            )
        )

    def test_parse_multiline_tokens(self):
        lines = parse_qr_token_lines("RMC-ATT-1-abc\nSTU-2, STU-3;")
        self.assertEqual(len(lines), 3)


class QrAttendanceApplyTests(SimpleTestCase):
    def test_apply_qr_sweep_delegates_rows(self):
        from apps.academics import qr_attendance

        with mock.patch.object(
            qr_attendance,
            "resolve_tokens_to_student_ids",
            return_value=([10, 11], []),
        ), mock.patch.object(
            qr_attendance,
            "apply_attendance_rows",
        ) as apply_rows:
            from apps.academics.bulk_attendance import BulkAttendanceResult

            apply_rows.return_value = BulkAttendanceResult(created=2, student_count=2)
            result = qr_attendance.apply_qr_sweep(
                classroom_id=5,
                date_value=date(2026, 5, 27),
                tokens_text="tok1\ntok2",
                school_id=1,
            )
            self.assertEqual(result.created, 2)
            apply_rows.assert_called_once()
            rows = apply_rows.call_args.kwargs["rows"]
            self.assertEqual(len(rows), 2)
