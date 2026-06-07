"""Wave E — auditor magic-link: time-bounded, PII-masked, access-logged grant."""

from __future__ import annotations

import uuid

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department
from apps.compliance import auditor_access
from apps.compliance.models import AuditorAccessGrant, AuditorAccessLog
from apps.compliance.pii_masking import mask_student_for_auditor
from apps.people.models import StudentProfile
from apps.schools.models import School


class AuditorAccessTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"AUD {uid}", slug=f"aud-{uid}", subdomain=f"aud{uid}", is_active=True
        )
        year = AcademicYear.objects.create(
            name="Y1", start_date="2025-01-01", end_date="2025-12-31", school=self.school
        )
        dept = Department.objects.create(name="D", code=f"D{uid}", school=self.school)
        classroom = Classroom.objects.create(
            academic_year=year, department=dept, name="Grade 5", code=f"C{uid}", school=self.school
        )
        self.student = StudentProfile.objects.create(
            first_name="Amara",
            last_name="Okoro",
            date_of_birth="2014-03-09",
            student_code=f"ST{uid}",
            parent_phone="+250788000111",
            school=self.school,
            classroom=classroom,
        )

    def test_masking_hides_pii(self):
        masked = mask_student_for_auditor(self.student)
        self.assertEqual(masked["initials"], "A.O.")
        self.assertEqual(masked["birth_year"], 2014)  # year only, no day/month
        self.assertEqual(masked["class"], "Grade 5")
        self.assertEqual(masked["guardian_contact"], "withheld")
        # full name + phone must not leak anywhere in the projection
        blob = str(masked)
        self.assertNotIn("Amara", blob)
        self.assertNotIn("Okoro", blob)
        self.assertNotIn("788000111", blob)

    def test_create_resolve_and_log(self):
        grant, token = auditor_access.create_grant(
            school_id=self.school.id, inspector_label="Ofsted Lead", ttl_hours=48
        )
        self.assertTrue(grant.is_valid())
        resolved = auditor_access.resolve_grant(token)
        self.assertEqual(resolved.id, grant.id)
        auditor_access.log_access(resolved, resource="auditor:roster", ip_address="10.0.0.5")
        self.assertEqual(AuditorAccessLog.objects.filter(grant=grant).count(), 1)
        roster = auditor_access.masked_roster_for_grant(grant)
        self.assertEqual(len(roster), 1)
        self.assertEqual(roster[0]["initials"], "A.O.")

    def test_bad_token_rejected(self):
        self.assertIsNone(auditor_access.resolve_grant("not-a-real-token"))
        self.assertIsNone(auditor_access.resolve_grant(""))

    def test_revoke_invalidates_token(self):
        grant, token = auditor_access.create_grant(school_id=self.school.id)
        self.assertIsNotNone(auditor_access.resolve_grant(token))
        self.assertTrue(auditor_access.revoke_grant(grant.id))
        self.assertIsNone(auditor_access.resolve_grant(token))  # revoked -> no access
        self.assertFalse(auditor_access.revoke_grant(grant.id))  # already revoked

    def test_expired_grant_rejected(self):
        grant, token = auditor_access.create_grant(school_id=self.school.id, ttl_hours=1)
        # force expiry
        grant.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        grant.save(update_fields=["expires_at"])
        self.assertFalse(grant.is_valid())
        self.assertIsNone(auditor_access.resolve_grant(token))


class AuditorInspectViewTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"AUDV {uid}", slug=f"audv-{uid}", subdomain=f"audv{uid}", is_active=True
        )

    def test_public_inspect_endpoint(self):
        from apps.compliance.views_auditor import auditor_inspect
        from django.test import RequestFactory

        grant, token = auditor_access.create_grant(
            school_id=self.school.id, inspector_label="State Inspector"
        )
        rf = RequestFactory()
        resp = auditor_inspect(rf.get(f"/compliance/auditor/inspect/?token={token}"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AuditorAccessLog.objects.filter(grant=grant).count(), 1)
        bad = auditor_inspect(rf.get("/compliance/auditor/inspect/?token=bogus"))
        self.assertEqual(bad.status_code, 403)
