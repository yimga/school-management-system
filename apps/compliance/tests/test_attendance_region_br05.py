"""BR-05 region packs + strict validate-on-write."""

from datetime import date
import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.academics.models import AcademicYear, Attendance, Classroom, Department
from apps.compliance.attendance_region_packs import get_resolved_attendance_pack
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class AttendanceRegionPackTests(TestCase):
    def test_usa_pack_requires_three_chars_when_strict(self):
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
            name="Pack School",
            slug=f"ps-{uuid.uuid4().hex[:10]}",
            subdomain=f"ps-{uuid.uuid4().hex[:10]}",
            default_region=region,
            features={"live_compliance_attendance_strict": True},
        )
        ay = AcademicYear.objects.create(
            school=school,
            name="Y1",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )
        dept = Department.objects.create(
            school=school,
            name="Dept",
            code=f"dp-{uuid.uuid4().hex[:12]}",
        )
        cl = Classroom.objects.create(
            school=school,
            academic_year=ay,
            department=dept,
            name="Form 1A",
            code=f"cl-{uuid.uuid4().hex[:12]}",
        )
        stu = StudentProfile.objects.create(
            school=school,
            first_name="Sam",
            last_name="Student",
            student_code=f"st-{uuid.uuid4().hex[:12]}",
            admission_number=f"ad-{uuid.uuid4().hex[:12]}",
        )
        att = Attendance(
            school=school,
            student=stu,
            classroom=cl,
            date=date.today(),
            status=Attendance.Status.ABSENT,
            remarks="ab",
        )
        pack = get_resolved_attendance_pack(att)
        self.assertEqual(pack.get("key"), "usa_attendance")
        with self.assertRaises(ValidationError):
            att.save()
        att.remarks = "ill note"
        att.save()
        self.assertIsNotNone(att.pk)

    def test_no_strict_allows_short_save(self):
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
            name="Pack School 2",
            slug=f"p2-{uuid.uuid4().hex[:10]}",
            subdomain=f"p2-{uuid.uuid4().hex[:10]}",
            default_region=region,
            features={},
        )
        ay = AcademicYear.objects.create(
            school=school,
            name="Y2",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )
        dept = Department.objects.create(
            school=school,
            name="Dept2",
            code=f"d2-{uuid.uuid4().hex[:12]}",
        )
        cl = Classroom.objects.create(
            school=school,
            academic_year=ay,
            department=dept,
            name="Form 1B",
            code=f"c2-{uuid.uuid4().hex[:12]}",
        )
        stu = StudentProfile.objects.create(
            school=school,
            first_name="Bo",
            last_name="B",
            student_code=f"s2-{uuid.uuid4().hex[:12]}",
            admission_number=f"a2-{uuid.uuid4().hex[:12]}",
        )
        Attendance.objects.create(
            school=school,
            student=stu,
            classroom=cl,
            date=date.today(),
            status=Attendance.Status.ABSENT,
            remarks="",
        )
