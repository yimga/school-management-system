"""S7 seal — WAL grade application is idempotent under at-least-once delivery.

``OfflineMarkEntry`` has no unique constraint, so the old
``bulk_create(rows, ignore_conflicts=True)`` deduped nothing — a re-delivered
WAL envelope inserted duplicate pending marks. These tests pin the natural-key
guard that mirrors the SODP grade applier: an already-pending (teacher,
subject_assignment, student, academic_year, term) is skipped, and duplicates
inside one batch collapse to a single row.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

_TEACHER = "apps.wal_stream.writers._resolve_teacher_id_from_envelope"
_IDS = "apps.wal_stream.writers._ids_in_school"
_FILTER = "apps.evals.models.OfflineMarkEntry.objects.filter"
_BULK = "apps.evals.models.OfflineMarkEntry.objects.bulk_create"


def _action(student_id=1):
    return {
        "student_id": student_id,
        "subject_assignment_id": 3,
        "academic_year_id": 1,
        "term_id": 1,
        "seq1_score": 80,
    }


class WalGradeIdempotencyTests(SimpleTestCase):
    def _run(self, actions, existing_keys):
        captured: list = []
        fake_qs = mock.Mock()
        fake_qs.values_list.return_value = existing_keys
        with mock.patch(_TEACHER, return_value=42), mock.patch(
            _IDS, side_effect=lambda model, ids, school_id, **kw: set(ids)
        ), mock.patch(_FILTER, return_value=fake_qs), mock.patch(
            _BULK, side_effect=lambda rows, **kw: captured.extend(rows)
        ):
            from apps.wal_stream.writers import _apply_grade

            _apply_grade({"school_id": 7, "user_id": 5, "actions": actions})
        return captured

    def test_duplicate_actions_in_one_batch_collapse(self):
        captured = self._run([_action(), _action()], existing_keys=[])
        self.assertEqual(len(captured), 1)

    def test_already_pending_row_is_skipped_on_retry(self):
        # (teacher, subject_assignment, student, academic_year, term) already pending.
        captured = self._run([_action()], existing_keys=[(42, 3, 1, 1, 1)])
        self.assertEqual(captured, [])

    def test_distinct_students_all_created(self):
        captured = self._run([_action(1), _action(2)], existing_keys=[])
        self.assertEqual({r.student_id for r in captured}, {1, 2})
