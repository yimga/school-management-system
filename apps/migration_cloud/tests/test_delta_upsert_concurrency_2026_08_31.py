"""Delta/upsert audit (2026-08-31): a re-import must be a FIELD-LEVEL patch.

Four properties were checked against the students + enrollment landers. Two
already held and are pinned here so they cannot rot; two failed and are closed
by ``_helpers.save_scoped``.

HOLDS  idempotence -- a second apply of the same artifact updates in place,
       creates no duplicate, and changes no column but ``updated_at``.
HOLDS  field-level patch (single-threaded) -- ``student_lander`` drops empty
       values out of ``defaults`` (student_lander.py:156), so a sparse
       re-import fills the column it carries and leaves the rest alone.
FAILED stale overwrite -- the ONLY student update path read the row, then wrote
       ALL ~35 columns back from that in-memory snapshot, reverting anything
       committed to the row in between. Apply runs one wave's artifacts in
       parallel threads (``orchestrator._run_waves``) and wave 1 holds both
       ``students`` and ``alumni``, which upsert the same StudentProfile rows --
       and the lander reported the reverted row as a clean update.
FAILED derived columns under a narrowed write -- ``save(update_fields=[...])``
       throws away what ``StudentProfile.save()`` generates for itself
       (``search_index``, a minted ``admission_number``). Pre-existing at
       student_lander.py:393 and :655; ``save_scoped`` now carries them, which
       is also what makes narrowing the update path safe.

NOT closed, and not closeable here: nothing orders two writers that both supply
the SAME field. The canonical students schema carries no version, epoch or
source timestamp to compare (apps/migration_cloud/ontology/catalog.py), so
last-writer-wins is the contract and ``MigrationConflict`` + a PRESERVE
resolution is the operator-facing mitigation. Narrowing removes the blast
radius, not the race.

SQLITE ONLY: these run on the sqlite test lane, where ``select_for_update`` is a
no-op -- nothing below proves Postgres lock or deadlock behaviour. The interleave
is made deterministic by committing the competing write from inside
``detect_conflict``, which both landers genuinely call between their read and
their save, rather than by racing real threads.
"""

from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud.landers import enrollment_lander as el
from apps.migration_cloud.landers import student_lander as sl
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.enrollment_lander import EnrollmentLander
from apps.migration_cloud.landers.student_lander import StudentLander
from apps.people.models import StudentProfile
from apps.schools.models import School

# A roster row carrying every first-class column StudentProfile models, so a
# later sparse file has something real to destroy.
FULL_ROW = {
    "external_id": "PS-D-001",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "gender": "F",
    "date_of_birth": "2010-04-01",
    "place_of_birth": "Buea",
    "joined_term": "Term 1",
    "section": "A",
    "exam_center_code": "CTR-9",
    "exam_system": "GCE",
    "parent_phone": "+237600000001",
}

# What the second file carries: the key, the name, and ONE newly-supplied phone.
PHONE_ONLY_ROW = {
    "external_id": "PS-D-001",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "parent_phone": "+237655555555",
}


class _RacingWrite:
    """Commit a competing write the first time the lander calls detect_conflict.

    ``detect_conflict`` runs between the lander's read of the existing row and
    its save, which is exactly the window a parallel wave thread writes into.
    Patching it makes that interleave deterministic without touching the code
    under test.
    """

    def __init__(self, module, pk, **values):
        self.module = module
        self.pk = pk
        self.values = values
        self.real = module.detect_conflict
        self.fired = False

    def __enter__(self):
        def racing(**kwargs):
            if not self.fired:
                self.fired = True
                StudentProfile.objects.filter(pk=self.pk).update(**self.values)
            return self.real(**kwargs)

        self.module.detect_conflict = racing
        return self

    def __exit__(self, *exc):
        self.module.detect_conflict = self.real
        return False


class DeltaUpsertPatchDisciplineTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Delta Upsert School",
            slug="delta-upsert-school",
            subdomain="delta-upsert-school",
            is_active=True,
            country_code="CM",
        )
        self.ctx = LanderContext(
            school=self.school, bundle_id=1, artifact_id=1, dry_run=False, schema_name=""
        )

    def _land(self, *rows):
        return StudentLander().land(
            canonical_rows=iter([dict(r) for r in rows]), ctx=self.ctx
        )

    def _snapshot(self, student):
        return {
            f.name: getattr(student, f.attname)
            for f in StudentProfile._meta.local_concrete_fields
        }

    # --- HOLDS: idempotence -------------------------------------------------

    def test_reapply_updates_in_place_and_churns_nothing_but_updated_at(self):
        first = self._land(FULL_ROW)
        self.assertEqual((first.created, first.quarantined), (1, 0), first.errors)
        student = StudentProfile.objects.get(school=self.school)
        before = self._snapshot(student)

        second = self._land(FULL_ROW)
        self.assertEqual(
            (second.created, second.updated, second.quarantined), (0, 1, 0), second.errors
        )
        self.assertEqual(StudentProfile.objects.filter(school=self.school).count(), 1)

        student.refresh_from_db()
        churned = {k for k, v in self._snapshot(student).items() if before[k] != v}
        # ``updated_at`` is auto_now, so every save moves it; nothing else may.
        self.assertEqual(churned, {"updated_at"})

    # --- HOLDS: field-level patch, single-threaded --------------------------

    def test_sparse_reimport_fills_the_new_column_and_keeps_the_others(self):
        self._land(FULL_ROW)
        result = self._land(PHONE_ONLY_ROW)
        self.assertEqual((result.updated, result.quarantined), (1, 0), result.errors)

        student = StudentProfile.objects.get(school=self.school)
        self.assertEqual(student.parent_phone, "+237655555555")
        # Columns the second file never mentioned survive it.
        self.assertEqual(student.gender, "F")
        self.assertEqual(str(student.date_of_birth), "2010-04-01")
        self.assertEqual(student.place_of_birth, "Buea")
        self.assertEqual(student.joined_term, "Term 1")
        self.assertEqual(student.section, "A")
        self.assertEqual(student.exam_center_code, "CTR-9")
        self.assertEqual(student.exam_system, "GCE")

    # --- CLOSED: the stale full-row overwrite -------------------------------

    def test_student_update_does_not_revert_a_write_committed_beside_it(self):
        """The real defect: a bare save() re-asserted columns the source file
        never carried, from a snapshot read before the competing write landed."""
        self._land(FULL_ROW)
        pk = StudentProfile.objects.get(school=self.school).pk

        with _RacingWrite(
            sl, pk, place_of_birth="Douala", exam_center_code="CTR-NEWER", section="Z"
        ) as race:
            result = self._land(PHONE_ONLY_ROW)
        self.assertTrue(race.fired, "the interleave never ran - this test proves nothing")

        # The lander calls this a clean update either way; that is what made the
        # revert silent, so assert it, then assert the data survived.
        self.assertEqual((result.updated, result.quarantined), (1, 0), result.errors)

        student = StudentProfile.objects.get(pk=pk)
        self.assertEqual(student.place_of_birth, "Douala")
        self.assertEqual(student.exam_center_code, "CTR-NEWER")
        self.assertEqual(student.section, "Z")
        # ...and the column this file DID carry is still applied.
        self.assertEqual(student.parent_phone, "+237655555555")

    def test_enrollment_update_does_not_revert_a_write_committed_beside_it(self):
        """Enrollment already scoped its write to ``updates``; pin it, so the
        student-side discipline and this one cannot drift apart again."""
        self._land(
            {
                "external_id": "PS-D-002",
                "admission_number": "PS-D-002",
                "first_name": "Grace",
                "last_name": "Hopper",
                "place_of_birth": "Limbe",
            }
        )
        pk = StudentProfile.objects.get(admission_number="PS-D-002").pk

        with _RacingWrite(el, pk, place_of_birth="Kumba", exam_center_code="CTR-E") as race:
            result = EnrollmentLander().land(
                canonical_rows=iter(
                    [
                        {
                            "student_external_id": "PS-D-002",
                            "enrollment_status": "active",
                            "section_code": "B",
                        }
                    ]
                ),
                ctx=self.ctx,
            )
        self.assertTrue(race.fired, "the interleave never ran - this test proves nothing")
        self.assertEqual(result.quarantined, 0, result.errors)

        student = StudentProfile.objects.get(pk=pk)
        self.assertEqual(student.place_of_birth, "Kumba")
        self.assertEqual(student.exam_center_code, "CTR-E")
        self.assertEqual(student.section, "B")

    # --- CLOSED: derived columns under a narrowed write ---------------------

    def test_name_correction_still_rebuilds_the_search_index(self):
        """``search_index`` is rebuilt inside ``StudentProfile.save()`` and is
        not a column any lander names, so narrowing the write without carrying
        it would leave a corrected pupil unfindable under their new name."""
        self._land(
            {"external_id": "PS-D-003", "first_name": "Adah", "last_name": "Lovelace"}
        )
        student = StudentProfile.objects.get(student_code="PS-D-003")
        self.assertIn("adah", student.search_index)

        self._land({"external_id": "PS-D-003", "first_name": "Ada", "last_name": "Byron"})
        student.refresh_from_db()
        self.assertEqual((student.first_name, student.last_name), ("Ada", "Byron"))
        self.assertIn("byron", student.search_index)
        self.assertNotIn("lovelace", student.search_index)

    def test_specialty_link_persists_the_admission_number_the_model_mints(self):
        """Setting the third of academic_year/specialty/classroom makes
        ``StudentProfile.save()`` mint an admission number. The specialty link
        saved ``update_fields=["specialty"]``, so the minted value never reached
        the row and the pupil kept an empty admission number for good."""
        from apps.academics.models import Specialty
        from apps.academics.structure_provisioning import ensure_general_department

        # Pass 1: the class label places the pupil (classroom + academic_year).
        self._land(
            {
                "external_id": "PS-D-004",
                "first_name": "Alan",
                "last_name": "Turing",
                "grade_level": "Form Two",
            }
        )
        student = StudentProfile.objects.get(student_code="PS-D-004")
        self.assertIsNotNone(student.classroom_id)
        self.assertIsNotNone(student.academic_year_id)

        Specialty.objects.create(
            school=self.school,
            name="Welding",
            code="WLD",
            department=ensure_general_department(self.school),
        )
        StudentProfile.objects.filter(pk=student.pk).update(admission_number="")

        # Pass 2: the roster now names the trade -> the specialty link fires and
        # completes the trio, so the model mints a number.
        self._land(
            {
                "external_id": "PS-D-004",
                "first_name": "Alan",
                "last_name": "Turing",
                "grade_level": "Form Two",
                "specialty": "Welding",
            }
        )
        student.refresh_from_db()
        self.assertIsNotNone(student.specialty_id)
        self.assertTrue(
            student.admission_number,
            "the model minted an admission number inside save() and the narrowed "
            "write discarded it",
        )


class StudentIdentityKeyResolutionTests(TestCase):
    """A history lander must resolve a pupil by the key the students lander
    landed them under.

    ``student_lander._lookup_field`` prefers ``student_code``; the shared
    ``_helpers.student_lookup_field`` had no ``student_code`` candidate at all
    and answered ``admission_number``. So a roster whose source id differs from
    its admission number -- the normal case -- landed the id in ``student_code``
    and every history file naming that id was quarantined as "no pupil carries
    the id", for a pupil that had landed in the same bundle.

    Closed by widening ``resolve_student`` to try the other identity columns
    AFTER the caller's own, never by reordering the caller's answer.
    """

    def setUp(self):
        self.school = School.objects.create(
            name="Identity Key School",
            slug="identity-key-school",
            subdomain="identity-key-school",
            is_active=True,
            country_code="CM",
        )
        self.ctx = LanderContext(
            school=self.school, bundle_id=1, artifact_id=1, dry_run=False, schema_name=""
        )

    def _enroll(self, student_external_id):
        return EnrollmentLander().land(
            canonical_rows=iter(
                [{"student_external_id": student_external_id, "enrollment_status": "active"}]
            ),
            ctx=self.ctx,
        )

    def test_history_row_resolves_by_the_source_id_the_roster_carried(self):
        # The roster carries BOTH, and they differ -- which is the normal export.
        StudentLander().land(
            canonical_rows=iter(
                [
                    {
                        "external_id": "PS-D-020",
                        "admission_number": "ADM-020",
                        "first_name": "Grace",
                        "last_name": "Hopper",
                    }
                ]
            ),
            ctx=self.ctx,
        )
        student = StudentProfile.objects.get(school=self.school)
        # The source id landed in student_code; admission_number kept the CSV's.
        self.assertEqual(student.student_code, "PS-D-020")
        self.assertEqual(student.admission_number, "ADM-020")

        # The enrollment file names the pupil by the source id, which is exactly
        # what the students ontology says external_id is for.
        result = self._enroll("PS-D-020")
        self.assertEqual(result.quarantined, 0, result.errors)
        self.assertEqual(result.updated, 1, result.errors)

    def test_the_admission_number_route_still_resolves(self):
        """The widening must not cost the lookup that already worked."""
        StudentLander().land(
            canonical_rows=iter(
                [
                    {
                        "external_id": "PS-D-021",
                        "admission_number": "ADM-021",
                        "first_name": "Ada",
                        "last_name": "Lovelace",
                    }
                ]
            ),
            ctx=self.ctx,
        )
        result = self._enroll("ADM-021")
        self.assertEqual(result.quarantined, 0, result.errors)
        self.assertEqual(result.updated, 1, result.errors)

    def test_a_cross_column_clash_still_resolves_to_the_pupil_it_resolves_to_today(self):
        """Nothing constrains student_code against admission_number across rows:
        StudentProfile.Meta carries three INDEPENDENT partial unique indexes. So
        one pupil's student_code may legally equal another's admission number.
        The caller's own column is tried first, so such a clash keeps resolving
        to the pupil it resolved to before the widening -- a wrong match is worse
        than a quarantine, and this cannot introduce a new one.
        """
        by_admission = StudentProfile.objects.create(
            school=self.school, first_name="Alan", last_name="Turing",
            student_code="CODE-A", admission_number="DUP",
        )
        by_code = StudentProfile.objects.create(
            school=self.school, first_name="Katherine", last_name="Johnson",
            student_code="DUP", admission_number="ADM-B",
        )
        self.assertNotEqual(by_admission.pk, by_code.pk)

        from apps.migration_cloud.landers._helpers import (
            model_field_names,
            resolve_student,
            student_lookup_field,
        )

        primary = student_lookup_field(model_field_names(StudentProfile))
        # The shared helper's answer is unchanged by the widening.
        self.assertEqual(primary, "admission_number")

        found = resolve_student(
            ctx=self.ctx,
            student_model=StudentProfile,
            lookup_field=primary,
            external_id="DUP",
            row={},
        )
        self.assertEqual(found.pk, by_admission.pk)
