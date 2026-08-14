"""G8 — a teacher roster's SUBJECTS/CLASSROOMS id-lists are preserved (no data
loss) and resolved to canonical names via the id-mapping layer where the
referenced entities landed in the same migration.
"""

from __future__ import annotations

import io
import types

from django.test import TestCase, TransactionTestCase

from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.landers.staff_lander import (
    _extract_teacher_id_lists,
    _split_id_list,
)
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)


class SplitIdListTests(TestCase):
    def test_splits_underscore_and_comma_lists_drops_nulls(self):
        self.assertEqual(_split_id_list("96_98_106_229_"), ["96", "98", "106", "229"])
        self.assertEqual(_split_id_list("12, 15 ; 7"), ["12", "15", "7"])
        self.assertEqual(_split_id_list("None"), [])
        self.assertEqual(_split_id_list(""), [])


class ExtractTeacherIdListsTests(TestCase):
    def test_partitions_subjects_and_classrooms_by_column_name(self):
        subs, classes = _extract_teacher_id_lists({
            "staff_external_id": "T1",
            "_unmapped.SUBJECTS": "96_98_106",
            "_unmapped.CLASSROOMS": "12_15",
        })
        self.assertEqual(subs, ["96", "98", "106"])
        self.assertEqual(classes, ["12", "15"])


def _xlsx_bytes(headers, rows):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _add_artifact(bundle, filename, headers, rows, sha):
    data = _xlsx_bytes(headers, rows)
    art = MigrationArtifact.objects.create(
        bundle=bundle, path_within_bundle=filename, filename=filename,
        detected_format=ArtifactFormat.XLSX, byte_size=len(data), sha256=sha,
    )
    store.capture_artifact_blob(
        art, types.SimpleNamespace(content_opener=lambda d=data: io.BytesIO(d))
    )


class TeacherTeachingHintsEndToEndTests(TransactionTestCase):
    def test_preserves_and_resolves_teacher_subject_ids(self):
        from apps.metadata.models import DynamicFieldValue
        from apps.migration_cloud.orchestrator import apply_bundle
        from apps.migration_cloud.pipeline import advance_bundle
        from apps.people.models import TeacherProfile
        from apps.schools.models import School

        school = School.objects.create(
            name="TVET Teach", subdomain="tvet-teach", country_code="CM",
        )
        bundle = MigrationBundle.objects.create(
            label="teach", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="teacher-hints", status=BundleStatus.INGESTING, school=school,
        )
        # Subjects added FIRST so their id-mappings exist when the teacher resolves
        # (both are wave 1; artifact order is preserved and workers=1 is serial).
        _add_artifact(
            bundle, "subjects.xlsx", ["SUBJECT NAME", "SUBJECT CODE"],
            [["Mathematics", "96"], ["Physics", "98"]], "a" * 64,
        )
        _add_artifact(
            bundle, "teachers.xlsx",
            ["TEACHER UNIQUE ID", "NAME", "EMAIL", "ROLE", "SUBJECTS"],
            [["T1", "Jane Doe", "jane@x.cm", "Teacher", "96_98_106"]], "b" * 64,
        )

        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        apply_bundle(bundle_id=bundle.pk, workers=1)

        teacher = TeacherProfile.objects.filter(school=school).first()
        self.assertIsNotNone(teacher, "teacher should land")

        def _dfv(field_key):
            row = DynamicFieldValue.objects.filter(
                entity_type="staff", entity_id=str(teacher.pk), field_key=field_key,
            ).first()
            return (row.value_json or {}).get("v") if row else None

        # Part A — the raw id-list is ALWAYS preserved (no data loss).
        raw = _dfv("source_subject_ids") or ""
        self.assertIn("96", raw)
        self.assertIn("106", raw)  # even the unresolved id is kept

        # Part B — resolved to canonical names via the id-mapping layer.
        resolved = _dfv("teaching_subjects") or ""
        self.assertIn("Mathematics", resolved)
        self.assertIn("Physics", resolved)
        self.assertNotIn("106", resolved)  # 106 didn't land → not resolved
