"""BR-05 degree enrollment region packs + strict + audit."""

from datetime import date
import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.academics.models import DegreeProgram, StudentDegreeEnrollment
from apps.compliance.enrollment_region_packs import get_resolved_enrollment_pack
from apps.people.models import StudentProfile
from apps.platform_runtime.models import PlatformEventLog
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class EnrollmentRegionPackTests(TestCase):
    def test_usa_strict_requires_start_date_when_active(self):
        region, _ = RegionConfig.objects.get_or_create(
            code="USA",
            defaults={
                "name": "United States",
                "default_language": "en",
                "timezone": "America/New_York",
                "date_format": "MM/DD/YYYY",
            },
        )
        school = School.objects.create(
            name="Enroll School",
            slug=f"es-{uuid.uuid4().hex[:10]}",
            subdomain=f"es-{uuid.uuid4().hex[:10]}",
            default_region=region,
            features={"live_compliance_enrollment_strict": True},
        )
        stu = StudentProfile.objects.create(
            school=school,
            first_name="Pat",
            last_name="Degree",
            student_code=f"st-{uuid.uuid4().hex[:12]}",
            admission_number=f"ad-{uuid.uuid4().hex[:12]}",
        )
        prog = DegreeProgram.objects.create(school=school, name="BSc CS")
        enr = StudentDegreeEnrollment(
            student=stu, program=prog, start_date=None, is_active=True
        )
        pack = get_resolved_enrollment_pack(enr)
        self.assertEqual(pack.get("key"), "usa_enrollment")
        with self.assertRaises(ValidationError):
            enr.save()
        enr.start_date = date(2025, 9, 1)
        enr.save()
        self.assertIsNotNone(enr.pk)

    def test_live_compliance_enrollment_emits_platform_event(self):
        region, _ = RegionConfig.objects.get_or_create(
            code="USA",
            defaults={
                "name": "United States",
                "default_language": "en",
                "timezone": "America/New_York",
                "date_format": "MM/DD/YYYY",
            },
        )
        school = School.objects.create(
            name="Audit Enroll",
            slug=f"ae-{uuid.uuid4().hex[:10]}",
            subdomain=f"ae-{uuid.uuid4().hex[:10]}",
            default_region=region,
            features={"live_compliance_enrollment": True},
        )
        stu = StudentProfile.objects.create(
            school=school,
            first_name="Alex",
            last_name="Audit",
            student_code=f"s3-{uuid.uuid4().hex[:12]}",
            admission_number=f"a3-{uuid.uuid4().hex[:12]}",
        )
        prog = DegreeProgram.objects.create(school=school, name="MSc")
        before = PlatformEventLog.objects.filter(
            event_type="live_compliance_enrollment"
        ).count()
        StudentDegreeEnrollment.objects.create(
            student=stu, program=prog, start_date=None, is_active=True
        )
        after = PlatformEventLog.objects.filter(
            event_type="live_compliance_enrollment"
        ).count()
        self.assertEqual(after, before + 1)
        row = (
            PlatformEventLog.objects.filter(event_type="live_compliance_enrollment")
            .order_by("-id")
            .first()
        )
        self.assertIn(
            "active_enrollment_missing_start_date", row.payload.get("issues", [])
        )
