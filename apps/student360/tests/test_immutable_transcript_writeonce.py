"""Immutable transcript is genuinely write-once (M29 / EOY final gap, Fix B).

The model was named ``ImmutableTranscript`` and documented as "never updated in
place", but ``create_immutable_transcript`` used ``update_or_create`` — so a
second call SILENTLY OVERWROTE the first frozen snapshot. These MUST-FIRE tests
lock the corrected contract:

* the default path is WRITE-ONCE — an existing snapshot is preserved, unchanged
  (this test FAILS on the pre-fix ``update_or_create`` code);
* ``allow_refreeze=True`` still overwrites — the deliberate, audited re-freeze
  (control; passes before and after).
"""

from django.test import TestCase

from apps.people.enrollment_services import ensure_enrollment
from apps.people.tests.test_enrollment import EnrollmentFixtureMixin
from apps.student360.models import ImmutableTranscript
from apps.student360.services import create_immutable_transcript


class ImmutableTranscriptWriteOnceTests(EnrollmentFixtureMixin, TestCase):
    def setUp(self):
        self.build_school("writeonce")
        self.student = self.make_student("WO-1")
        # Real evaluation data so build_transcript_snapshot yields a snapshot
        # and the first freeze actually creates a row.
        self.score(self.student, 16, 15, 17)
        ensure_enrollment(self.student)

    def _freeze_first(self):
        obj = create_immutable_transcript(self.student, self.year_1)
        self.assertIsNotNone(obj, "first freeze must create a transcript row")
        return obj

    def test_default_is_write_once_does_not_overwrite(self):
        first = self._freeze_first()
        # Stamp a sentinel directly into the stored snapshot so we can prove the
        # second freeze does NOT rebuild/replace it.
        ImmutableTranscript.objects.filter(pk=first.pk).update(
            snapshot={"marker": "ORIGINAL"}
        )

        # Second freeze, DEFAULT (write-once): must return the SAME row untouched.
        again = create_immutable_transcript(self.student, self.year_1)
        self.assertIsNotNone(again)
        self.assertEqual(again.pk, first.pk)

        # Still exactly one canonical row, and its snapshot is the untouched
        # sentinel — the "immutable" snapshot was NOT silently overwritten.
        self.assertEqual(
            ImmutableTranscript.objects.filter(
                student=self.student, academic_year=self.year_1
            ).count(),
            1,
        )
        stored = ImmutableTranscript.objects.get(pk=first.pk)
        self.assertEqual(
            stored.snapshot,
            {"marker": "ORIGINAL"},
            "default create_immutable_transcript must NOT overwrite an existing "
            "immutable snapshot",
        )

    def test_allow_refreeze_true_overwrites(self):
        first = self._freeze_first()
        ImmutableTranscript.objects.filter(pk=first.pk).update(
            snapshot={"marker": "ORIGINAL"}
        )

        again = create_immutable_transcript(
            self.student, self.year_1, allow_refreeze=True
        )
        self.assertIsNotNone(again)
        self.assertEqual(again.pk, first.pk)  # same row, updated in place

        stored = ImmutableTranscript.objects.get(pk=first.pk)
        self.assertNotEqual(
            stored.snapshot,
            {"marker": "ORIGINAL"},
            "allow_refreeze=True must replace the stored snapshot",
        )
        # And it is a genuinely rebuilt snapshot, not the sentinel.
        self.assertIn("academic_year_id", stored.snapshot)
