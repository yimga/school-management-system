"""A held row must keep the row, and say why it was held.

Step 1 + 2 of ``docs/MIGRATION_CLOUD_ZERO_TOUCH_IMPORT_SPEC.md``.

Bundle 84 held 442 rows "for review" and nobody could review them. The reason was
structural, not cosmetic: 29 of 35 lander files threw the offending row away and
kept an English sentence plus a ``row_index`` that was the position in the ERROR
LIST, not in the source file. **You cannot replay a row you did not keep**, so no
remediator — however good — could ever have resolved one of those rows.

The second half was the reason. ``issue_class`` decides whether a row needs a
human at all, and it was decided by searching the error text for ``"duplicate"``,
``"not found"``, ``"missing"``. Measured across all 106 per-row failure sites, 60
fell through to ``lander_error`` — "a person must look at this" — including
``no team named X (catalog not landed yet)``, which is a wave-ordering reference
failure that resolves itself.

DB-free (``SimpleTestCase``) so these run without the shared test database.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.migration_cloud.landers import reason_codes
from apps.migration_cloud.landers._helpers import record_row_error, record_row_note
from apps.migration_cloud.landers.base import LanderResult

ROW_A = {"student_external_id": "S-1", "name": "Ada", "date": "2026-01-05"}
ROW_B = {"student_external_id": "S-2", "name": "Grace", "date": "2026-01-06"}


class RecordRowErrorKeepsTheRowTests(SimpleTestCase):
    def test_it_counts_the_row_and_keeps_the_message(self):
        result = LanderResult()
        record_row_error(result, ROW_A, "boom", reason_code=reason_codes.LANDER_ERROR)
        self.assertEqual(result.quarantined, 1)
        self.assertEqual(result.errors, ["boom"])

    def test_the_source_row_survives(self):
        result = LanderResult()
        record_row_error(result, ROW_A, "boom", reason_code=reason_codes.LANDER_ERROR)
        self.assertEqual(result.error_rows[0]["row"]["student_external_id"], "S-1")

    def test_a_non_dict_row_is_still_kept(self):
        result = LanderResult()
        record_row_error(result, "raw line", "boom", reason_code=reason_codes.LANDER_ERROR)
        self.assertEqual(result.error_rows[0]["row"], {"_value": "raw line"})

    def test_errors_and_error_rows_stay_in_lockstep(self):
        result = LanderResult()
        for i in range(5):
            record_row_error(
                result, {"i": i}, f"boom {i}", reason_code=reason_codes.LANDER_ERROR
            )
        self.assertEqual(len(result.errors), len(result.error_rows))
        for err, entry in zip(result.errors, result.error_rows):
            self.assertEqual(err, entry["error"])

    def test_two_rows_failing_with_the_SAME_message_each_keep_their_own_row(self):
        """The bug positional pairing exists to fix.

        The orchestrator used to build a ``{error_string: row}`` dict, so an error
        message that does not interpolate the row — which is most of them —
        collapsed every failing row onto one entry and all but the last lost its
        snapshot entirely.
        """
        result = LanderResult()
        record_row_error(result, ROW_A, "identical", reason_code=reason_codes.INVALID_REF)
        record_row_error(result, ROW_B, "identical", reason_code=reason_codes.INVALID_REF)
        kept = [e["row"]["student_external_id"] for e in result.error_rows]
        self.assertEqual(kept, ["S-1", "S-2"])

    def test_the_offending_field_is_recorded_when_known(self):
        result = LanderResult()
        record_row_error(
            result,
            ROW_A,
            "missing dob",
            reason_code=reason_codes.MISSING_REQUIRED,
            field="date_of_birth",
        )
        self.assertEqual(result.error_rows[0]["field"], "date_of_birth")

    def test_no_field_is_none_not_a_guess(self):
        result = LanderResult()
        record_row_error(result, ROW_A, "boom", reason_code=reason_codes.LANDER_ERROR)
        self.assertIsNone(result.error_rows[0]["field"])


class TheReasonIsDeclaredNotGuessedTests(SimpleTestCase):
    def test_a_declared_code_is_recorded_as_declared(self):
        result = LanderResult()
        record_row_error(result, ROW_A, "boom", reason_code=reason_codes.INVALID_REF)
        entry = result.error_rows[0]
        self.assertEqual(entry["reason_code"], "invalid_ref")
        self.assertEqual(entry["reason_source"], "declared")

    def test_a_declared_code_beats_what_the_text_would_have_said(self):
        """The whole point: the words stop deciding."""
        result = LanderResult()
        record_row_error(
            result, ROW_A, "missing everything", reason_code=reason_codes.INVALID_REF
        )
        self.assertEqual(result.error_rows[0]["reason_code"], "invalid_ref")

    def test_omitting_the_code_falls_back_and_says_so(self):
        result = LanderResult()
        record_row_error(result, ROW_A, "student not found")
        entry = result.error_rows[0]
        self.assertEqual(entry["reason_code"], "invalid_ref")
        self.assertEqual(entry["reason_source"], "fallback")

    def test_an_unknown_code_is_not_stored(self):
        """An issue_class the review surface has no label for renders to a school
        as a title-cased slug — worse than a class we can explain."""
        result = LanderResult()
        record_row_error(result, ROW_A, "row is missing a name", reason_code="banana")
        entry = result.error_rows[0]
        self.assertEqual(entry["reason_code"], "missing_required")
        self.assertEqual(entry["reason_source"], "fallback")

    def test_the_vocabulary_is_exactly_what_the_review_surface_speaks(self):
        from apps.migration_cloud.views import QUARANTINE_ISSUE_LABELS

        self.assertEqual(
            set(reason_codes.ALL_REASON_CODES), set(QUARANTINE_ISSUE_LABELS)
        )

    def test_no_action_classes_agree_with_the_view_layer(self):
        from apps.migration_cloud.views import QUARANTINE_NO_ACTION_CLASSES

        self.assertEqual(
            set(reason_codes.NO_ACTION_REASON_CODES), set(QUARANTINE_NO_ACTION_CLASSES)
        )


class TheFallbackClassifierIsUnchangedTests(SimpleTestCase):
    """A row that has NOT been reviewed must not be silently reclassified by this
    work. The fallback keeps the exact answers the old orchestrator gave."""

    CASES = [
        ("source marked this row deleted — held for review", "source_deletion"),
        ("duplicate external_id", "duplicate"),
        ("row already exists", "duplicate"),
        ("invalid date", "invalid_ref"),
        ("student not found", "invalid_ref"),
        ("unresolved student", "invalid_ref"),
        ("missing student/term", "missing_required"),
        ("required column absent", "missing_required"),
        ("upsert failed: IntegrityError", "lander_error"),
        ("", "lander_error"),
    ]

    def test_each_legacy_case(self):
        for message, expected in self.CASES:
            with self.subTest(message=message):
                self.assertEqual(reason_codes.classify_message(message), expected)

    def test_the_orchestrator_still_answers_the_same_way(self):
        from apps.migration_cloud.orchestrator import _classify_quarantine_issue

        for message, expected in self.CASES:
            with self.subTest(message=message):
                self.assertEqual(_classify_quarantine_issue(message), expected)


class TheMisroutedMessagesAreNowRoutedRightTests(SimpleTestCase):
    """The measured win, stated as the cases it changes.

    Each message below is a real lander error. The substring matcher sends every
    one of them to ``lander_error`` — the bucket that means a person must look at
    it — and every one of them is something else.
    """

    MISROUTED = [
        ("athletics_fixtures[row=3]: no team named X (catalog not landed yet)", "invalid_ref"),
        ("communications: no recipient resolved for parent P-1", "invalid_ref"),
        ("finance: no compliance profile available for invoice INV-1", "invalid_ref"),
        ("grades: subject assignment has no teacher with a TeacherProfile for S-1", "invalid_ref"),
        ("No student with external_id='S-9' for guardian", "invalid_ref"),
        ("staff EMP-2: no linkable user", "invalid_ref"),
        ("grades: no score or letter for S-1 / Maths / T1", "missing_required"),
        ("payroll: this row does not say which staff member it belongs to", "missing_required"),
    ]

    def test_the_matcher_gets_all_of_them_wrong(self):
        for message, _correct in self.MISROUTED:
            with self.subTest(message=message):
                self.assertEqual(reason_codes.classify_message(message), "lander_error")

    def test_declaring_the_code_routes_them_correctly(self):
        for message, correct in self.MISROUTED:
            with self.subTest(message=message):
                result = LanderResult()
                record_row_error(result, ROW_A, message, reason_code=correct)
                self.assertEqual(result.error_rows[0]["reason_code"], correct)


class ANoteIsNotAHeldRowTests(SimpleTestCase):
    """Twelve sites appended to ``errors`` without incrementing ``quarantined``,
    so each minted a quarantine record the board's held count never included."""

    def test_a_note_does_not_count_as_held(self):
        result = LanderResult()
        record_row_note(result, "custom_attributes sweep failed for staff 12")
        self.assertEqual(result.quarantined, 0)

    def test_a_note_never_lands_in_errors(self):
        result = LanderResult()
        record_row_note(result, "extras write failed")
        self.assertEqual(result.errors, [])
        self.assertEqual(result.error_rows, [])

    def test_a_note_is_still_kept(self):
        """Not counted is not the same as hidden."""
        result = LanderResult()
        record_row_note(result, "extras write failed")
        self.assertEqual(result.notes, [{"note": "extras write failed"}])

    def test_held_rows_and_durable_records_agree(self):
        result = LanderResult()
        record_row_error(result, ROW_A, "boom", reason_code=reason_codes.LANDER_ERROR)
        record_row_note(result, "sweep failed")
        record_row_error(result, ROW_B, "bang", reason_code=reason_codes.LANDER_ERROR)
        self.assertEqual(result.quarantined, len(result.errors))
        self.assertEqual(result.quarantined, len(result.error_rows))


class _Recorder:
    """Stands in for MigrationQuarantineRecord.objects."""

    def __init__(self):
        self.created: list[dict] = []

    @property
    def objects(self):
        return self

    def create(self, **kwargs):
        self.created.append(kwargs)
        return SimpleNamespace(pk=len(self.created))


@contextlib.contextmanager
def _null_atomic(*args, **kwargs):
    yield


class TheOrchestratorWritesWhatTheLanderDeclaredTests(SimpleTestCase):
    """``_quarantine_errors`` with the DB stubbed out — the pairing and the
    classification are the logic under test, not Django's writer."""

    def _run(self, result):
        from apps.migration_cloud import orchestrator

        recorder = _Recorder()
        bundle = SimpleNamespace(pk=84, school=SimpleNamespace(pk=1))
        artifact = SimpleNamespace(path_within_bundle="students.csv")
        fake_models = SimpleNamespace(
            MigrationQuarantineRecord=SimpleNamespace(
                objects=recorder, Status=SimpleNamespace(PENDING="PENDING")
            )
        )
        with patch.dict(
            "sys.modules", {"apps.automation.models": fake_models}
        ), patch.object(
            orchestrator, "transaction", SimpleNamespace(atomic=_null_atomic)
        ):
            orchestrator._quarantine_errors(
                bundle=bundle,
                run=SimpleNamespace(pk=7),
                artifact=artifact,
                domain="students",
                result=result,
            )
        return recorder.created

    def test_the_declared_class_is_what_gets_stored(self):
        result = LanderResult()
        record_row_error(
            result, ROW_A, "no team named X", reason_code=reason_codes.INVALID_REF
        )
        rows = self._run(result)
        self.assertEqual(rows[0]["issue_class"], "invalid_ref")
        self.assertEqual(rows[0]["payload"]["reason_source"], "declared")

    def test_each_record_carries_its_OWN_source_row(self):
        result = LanderResult()
        record_row_error(result, ROW_A, "identical", reason_code=reason_codes.INVALID_REF)
        record_row_error(result, ROW_B, "identical", reason_code=reason_codes.INVALID_REF)
        rows = self._run(result)
        self.assertEqual(
            [r["payload"]["source_row"]["student_external_id"] for r in rows],
            ["S-1", "S-2"],
        )

    def test_the_field_reaches_the_record(self):
        result = LanderResult()
        record_row_error(
            result,
            ROW_A,
            "missing dob",
            reason_code=reason_codes.MISSING_REQUIRED,
            field="date_of_birth",
        )
        rows = self._run(result)
        self.assertEqual(rows[0]["payload"]["field"], "date_of_birth")

    def test_a_bare_string_still_lands_marked_as_a_guess(self):
        """Back-compat: a lander that has not adopted the contract still works."""
        result = LanderResult()
        result.quarantined += 1
        result.errors.append("student not found")  # lander-contract-allow: test fixture
        rows = self._run(result)
        self.assertEqual(rows[0]["issue_class"], "invalid_ref")
        self.assertEqual(rows[0]["payload"]["reason_source"], "fallback")
        self.assertNotIn("source_row", rows[0]["payload"])

    def test_misaligned_lists_fall_back_to_message_pairing_rather_than_shifting(self):
        """A lander mixing both styles must not shift rows onto the wrong error."""
        result = LanderResult()
        record_row_error(result, ROW_A, "kept", reason_code=reason_codes.INVALID_REF)
        result.quarantined += 1
        result.errors.append("bare")  # lander-contract-allow: test fixture
        rows = self._run(result)
        by_error = {r["payload"]["error"]: r["payload"] for r in rows}
        self.assertEqual(by_error["kept"]["source_row"]["student_external_id"], "S-1")
        self.assertNotIn("source_row", by_error["bare"])

    def test_notes_never_become_quarantine_records(self):
        result = LanderResult()
        record_row_note(result, "sweep failed for staff 12")
        self.assertEqual(self._run(result), [])

    def test_the_record_count_equals_the_held_count(self):
        result = LanderResult()
        for i in range(4):
            record_row_error(
                result, {"i": i}, f"boom {i}", reason_code=reason_codes.LANDER_ERROR
            )
        record_row_note(result, "sweep failed")
        self.assertEqual(len(self._run(result)), result.quarantined)
