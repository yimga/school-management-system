from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department
from apps.communication.models import (
    AlertRule,
    ContactRequest,
    ContactRequestAttachment,
    DirectConversation,
    Message,
    MessageThread,
    ThreadMessage,
)
from apps.communication.forms_groups import MessageThreadCreateForm
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import RegionConfig


class CommunicationTenantScopeTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            slug="tenant-scope-school",
            subdomain="tenant-scope-school",
            name="Tenant Scope School",
            default_region=self.region,
            timezone=self.region.timezone,
        )
        self.other_school = School.objects.create(
            slug="tenant-scope-other",
            subdomain="tenant-scope-other",
            name="Tenant Scope Other",
            default_region=self.region,
            timezone=self.region.timezone,
        )

        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
            school=self.school,
        )
        self.department = Department.objects.create(
            name="Science",
            code="SCI-TENANT",
            school=self.school,
        )
        self.other_department = Department.objects.create(
            name="Arts",
            code="ART-TENANT",
            school=self.other_school,
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 2A",
            code="F2A-TENANT",
            school=self.school,
        )

        self.staff = User.objects.create_user(
            username="tenant_staff",
            password="pass12345",
            role=User.Role.TEACHER,
        )
        self.parent = User.objects.create_user(
            username="tenant_parent",
            password="pass12345",
            role=User.Role.PARENT,
        )
        self.other_staff = User.objects.create_user(
            username="other_tenant_staff",
            password="pass12345",
            role=User.Role.TEACHER,
        )

        SchoolMembership.objects.create(
            user=self.staff, school=self.school, role=User.Role.TEACHER, is_primary=True
        )
        SchoolMembership.objects.create(
            user=self.parent, school=self.school, role=User.Role.PARENT, is_primary=True
        )
        SchoolMembership.objects.create(
            user=self.other_staff,
            school=self.other_school,
            role=User.Role.TEACHER,
            is_primary=True,
        )

        TeacherProfile.objects.create(user=self.staff, school=self.school)
        TeacherProfile.objects.create(user=self.other_staff, school=self.other_school)
        self.student = StudentProfile.objects.create(
            first_name="Tenant",
            last_name="Student",
            student_code="TEN-STU-001",
            academic_year=self.year,
            classroom=self.classroom,
            school=self.school,
            is_active=True,
        )

    def test_message_auto_sets_school(self):
        message = Message.objects.create(
            sender=self.staff,
            recipient=self.parent,
            subject="Welcome",
            body="Hello parent",
        )
        self.assertEqual(message.school_id, self.school.id)

    def test_thread_and_thread_message_auto_set_school(self):
        thread = MessageThread.objects.create(
            title="Class Updates",
            scope=MessageThread.Scope.CLASSROOM,
            classroom=self.classroom,
            created_by=self.staff,
        )
        message = ThreadMessage.objects.create(
            thread=thread,
            author=self.staff,
            content="Weekly recap",
        )
        self.assertEqual(thread.school_id, self.school.id)
        self.assertEqual(message.school_id, self.school.id)

    def test_contact_request_and_attachment_auto_set_school(self):
        contact_request = ContactRequest.objects.create(
            parent=self.parent,
            student=self.student,
            contact_name="Parent One",
            contact_phone="+123456789",
            contact_email="parent@example.com",
            subject="Need meeting",
            message="Please schedule a meeting.",
        )
        attachment = ContactRequestAttachment.objects.create(
            request=contact_request,
            uploaded_by=self.staff,
            file=SimpleUploadedFile(
                "proof.pdf", b"%PDF-1.4 mock", content_type="application/pdf"
            ),
        )
        self.assertEqual(contact_request.school_id, self.school.id)
        self.assertEqual(attachment.school_id, self.school.id)

    def test_direct_conversation_and_alert_rule_auto_set_school(self):
        conversation = DirectConversation.objects.create(
            user1=self.staff,
            user2=self.parent,
        )
        alert_rule = AlertRule.objects.create(
            user=self.staff,
            name="Absence Alerts",
            condition="attendance_absent > 0",
            frequency=AlertRule.Frequency.DAILY,
        )
        self.assertEqual(conversation.school_id, self.school.id)
        self.assertEqual(alert_rule.school_id, self.school.id)

    def test_group_form_querysets_are_tenant_scoped(self):
        form = MessageThreadCreateForm(user=self.staff, school=self.school)

        self.assertQuerySetEqual(
            form.fields["department"].queryset.order_by("id"),
            Department.objects.filter(school=self.school).order_by("id"),
            transform=lambda obj: obj,
        )
        self.assertIn(self.staff, form.fields["members"].queryset)
        self.assertIn(self.parent, form.fields["members"].queryset)
        self.assertNotIn(self.other_staff, form.fields["members"].queryset)
        self.assertNotIn(self.other_department, form.fields["department"].queryset)
