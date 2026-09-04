"""G6 — parent/guardian NAME preserved as a student-scoped claimable hint AND
promoted into the live Guardian directory (unusable-password PARENT account).
"""

from __future__ import annotations

import io
import types

from django.test import TestCase

from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.landers.student_lander import _extract_guardian_hint
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)


class ExtractGuardianHintTests(TestCase):
    def test_reads_parent_name_from_passthrough_columns(self):
        # Unmapped "Parent" column + a custom_fields guardian phone.
        name, phone = _extract_guardian_hint({
            "first_name": "Ada",
            "_unmapped.Parent": "Andoh Julius",
            "custom_fields.guardian_phone": "+237690000001",
        })
        self.assertEqual(name, "Andoh Julius")
        self.assertEqual(phone, "+237690000001")

    def test_ignores_null_literals_and_non_name_columns(self):
        name, phone = _extract_guardian_hint({
            "_unmapped.Parent": "None",           # null literal -> dropped
            "custom_fields.parent_email": "a@b.cm",  # email -> not a name
        })
        self.assertEqual(name, "")
        self.assertEqual(phone, "")

    def test_non_guardian_columns_are_not_captured(self):
        name, phone = _extract_guardian_hint({
            "_unmapped.Religion": "Catholic",
            "custom_fields.house": "Blue",
        })
        self.assertEqual((name, phone), ("", ""))


class UnclaimedGuardianHintHelperTests(TestCase):
    def test_reads_student_scoped_hint(self):
        from apps.metadata.models import DynamicFieldValue
        from apps.portal.services import unclaimed_guardian_hint
        from apps.schools.models import School
        from apps.people.models import StudentProfile

        school = School.objects.create(name="H", subdomain="h-hint")
        student = StudentProfile.objects.create(
            school=school, first_name="Ada", last_name="Lovelace",
        )
        DynamicFieldValue.objects.create(
            school=school, entity_type="student", entity_id=str(student.pk),
            field_key="parent_name", value_json={"v": "Andoh Julius"},
        )
        hint = unclaimed_guardian_hint(student)
        self.assertEqual(hint, {"name": "Andoh Julius"})

    def test_no_hint_returns_none(self):
        from apps.portal.services import unclaimed_guardian_hint
        from apps.schools.models import School
        from apps.people.models import StudentProfile

        school = School.objects.create(name="H2", subdomain="h2-hint")
        student = StudentProfile.objects.create(school=school, first_name="No", last_name="Hint")
        self.assertIsNone(unclaimed_guardian_hint(student))


class LinkChildFormSurfacesHintTests(TestCase):
    def test_form_exposes_guardian_hint_on_valid_admission_number(self):
        from apps.accounts.models import User
        from apps.metadata.models import DynamicFieldValue
        from apps.people.models import StudentGuardian, StudentProfile
        from apps.portal.forms import LinkChildForm
        from apps.schools.models import School

        school = School.objects.create(name="Claim", subdomain="claim-hint")
        student = StudentProfile.objects.create(
            school=school, first_name="Ada", last_name="Lovelace",
            admission_number="CLAIM123", is_active=True,
        )
        DynamicFieldValue.objects.create(
            school=school, entity_type="student", entity_id=str(student.pk),
            field_key="parent_name", value_json={"v": "Andoh Julius"},
        )
        parent = User.objects.create_user(username="claim.parent", email="p@claim.cm")
        if hasattr(parent, "role"):
            parent.role = User.Role.PARENT
            parent.save(update_fields=["role"])

        form = LinkChildForm(
            {
                "admission_number": "CLAIM123",
                "relationship": StudentGuardian.Relationship.GUARDIAN,
                "preferred_contact": StudentGuardian.PreferredContact.EMAIL,
            },
            guardian_user=parent, policy={}, school=school, school_code="SCH",
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(getattr(form, "guardian_hint", None), {"name": "Andoh Julius"})


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


class GuardianHintIngestEndToEndTests(TestCase):
    def test_parent_name_persists_and_lands_in_guardian_directory(self):
        from apps.accounts.models import User
        from apps.metadata.models import DynamicFieldValue
        from apps.migration_cloud.orchestrator import apply_bundle
        from apps.migration_cloud.pipeline import advance_bundle
        from apps.people.models import StudentGuardian, StudentProfile
        from apps.schools.models import School, SchoolMembership

        school = School.objects.create(
            name="TVET Hint", subdomain="tvet-hint", country_code="CM",
        )
        bundle = MigrationBundle.objects.create(
            label="hint", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="guardian-hint", status=BundleStatus.INGESTING, school=school,
        )
        data = _xlsx_bytes(
            ["ID", "Name", "Gender", "Date of Birth", "Class", "Parent"],
            [["247", "ACHU DECLAN", "Female", "2012-11-16", "Form Two", "Andoh Julius"],
             ["248", "EYONG SHARON", "Female", "2012-02-03", "Form Two", "None"]],
        )
        art = MigrationArtifact.objects.create(
            bundle=bundle, path_within_bundle="students.xlsx", filename="students.xlsx",
            detected_format=ArtifactFormat.XLSX, byte_size=len(data), sha256="d" * 64,
        )
        store.capture_artifact_blob(art, types.SimpleNamespace(content_opener=lambda: io.BytesIO(data)))

        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        apply_bundle(bundle_id=bundle.pk, workers=1)

        andoh = StudentProfile.objects.filter(school=school, first_name="ACHU").first()
        self.assertIsNotNone(andoh)
        # The parent NAME is preserved, student-scoped and joinable.
        self.assertTrue(
            DynamicFieldValue.objects.filter(
                entity_type="student", entity_id=str(andoh.pk), field_key="parent_name",
            ).exists(),
            "parent name should persist as a student-scoped hint",
        )
        link = StudentGuardian.objects.filter(student=andoh).select_related("guardian_user").first()
        self.assertIsNotNone(link, "Parent column must appear in the Guardians directory")
        self.assertEqual(link.guardian_user.role, User.Role.PARENT)
        self.assertFalse(link.guardian_user.has_usable_password())
        self.assertTrue(
            SchoolMembership.objects.filter(
                school=school, user=link.guardian_user, role=User.Role.PARENT,
            ).exists()
        )
        # The 'None' literal is NOT stored as a hint and must not mint a guardian.
        sharon = StudentProfile.objects.filter(school=school, first_name="EYONG").first()
        self.assertIsNotNone(sharon)
        self.assertFalse(
            DynamicFieldValue.objects.filter(
                entity_type="student", entity_id=str(sharon.pk), field_key="parent_name",
            ).exists(),
            "a 'None' literal must not become a hint",
        )
        self.assertFalse(StudentGuardian.objects.filter(student=sharon).exists())
