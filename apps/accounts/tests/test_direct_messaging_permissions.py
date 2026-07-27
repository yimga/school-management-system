"""Direct-messaging RBAC — including the parent two-way inbox.

Parents may DM their children's teachers and the school office (a curated,
RBAC-scoped picker), but never other parents or students. This suite is built
on a realistic tenant (School + memberships + guardian/teacher graph) so the
school-scoped messaging views actually resolve recipients — the earlier setup
created bare users with no school and could not exercise the hardened views.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.accounts.models import User
from apps.communication.models import DirectConversation, Message
from apps.evals.models import TeacherAssignment
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.schools.models import School, SchoolMembership


class DirectMessagingPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="DM School", slug="dm-school", subdomain="dm-school", is_active=True
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        cls.term = Term.objects.create(
            school=cls.school,
            academic_year=cls.year,
            name="FIRST",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        cls.dept = Department.objects.create(
            school=cls.school, name="Science", code="SCI-DM"
        )
        cls.specialty = Specialty.objects.create(
            school=cls.school, department=cls.dept, name="General", code="GEN-DM"
        )
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=cls.dept,
            name="Form 3A",
            code="F3A-DM",
        )

        # The teacher of the parent's child (assigned to the child's classroom).
        teacher_user = User.objects.create_user(
            username="teacher_dm", password="pass", role=User.Role.TEACHER
        )
        cls.teacher = teacher_user
        cls.teacher_profile = TeacherProfile.objects.create(
            user=teacher_user, school=cls.school
        )
        subject = Subject.objects.create(school=cls.school, name="Physics")
        sa = SubjectAssignment.objects.create(
            school=cls.school,
            academic_year=cls.year,
            term=cls.term,
            classroom=cls.classroom,
            specialty=cls.specialty,
            subject=subject,
            coefficient=1,
        )
        TeacherAssignment.objects.create(
            school=cls.school,
            teacher=cls.teacher_profile,
            academic_year=cls.year,
            subject_assignment=sa,
        )

        # A teacher who does NOT teach the parent's child (not in the parent's set).
        other_teacher_user = User.objects.create_user(
            username="teacher_other_dm", password="pass", role=User.Role.TEACHER
        )
        cls.other_teacher = other_teacher_user
        TeacherProfile.objects.create(user=other_teacher_user, school=cls.school)

        # Principal / front office — staff a parent can always reach.
        cls.principal = User.objects.create_user(
            username="principal_dm",
            password="pass",
            role=User.Role.PRINCIPAL,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=cls.principal, school=cls.school, role=User.Role.PRINCIPAL, is_primary=True
        )

        # Parent + their child.
        cls.parent = User.objects.create_user(
            username="parent_dm", password="pass", role=User.Role.PARENT
        )
        SchoolMembership.objects.create(
            user=cls.parent, school=cls.school, role=User.Role.PARENT, is_primary=True
        )
        cls.child = StudentProfile.objects.create(
            first_name="Kid",
            last_name="DM",
            student_code="STU-DM-1",
            classroom=cls.classroom,
            academic_year=cls.year,
            specialty=cls.specialty,
            school=cls.school,
        )
        StudentGuardian.objects.create(
            guardian_user=cls.parent,
            student=cls.child,
            relationship=StudentGuardian.Relationship.GUARDIAN,
        )

        # A second, unrelated parent (parents must not DM each other).
        cls.other_parent = User.objects.create_user(
            username="parent_other_dm", password="pass", role=User.Role.PARENT
        )
        SchoolMembership.objects.create(
            user=cls.other_parent,
            school=cls.school,
            role=User.Role.PARENT,
            is_primary=True,
        )

        # A student login (parents must not DM students).
        cls.student = User.objects.create_user(
            username="student_dm", password="pass", role=User.Role.STUDENT
        )
        SchoolMembership.objects.create(
            user=cls.student, school=cls.school, role=User.Role.STUDENT, is_primary=True
        )

    # --- staff / student baselines -------------------------------------------

    def test_principal_can_send_direct_message(self):
        self.client.force_login(self.principal)
        response = self.client.post(
            reverse("accounts:direct_compose"),
            {
                "recipient": str(self.teacher.id),
                "subject": "Check-in",
                "body": "Please update marks by noon.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Message.objects.filter(
                sender=self.principal,
                recipient=self.teacher,
                body="Please update marks by noon.",
            ).exists()
        )

    def test_student_cannot_open_direct_compose(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:direct_compose"))
        self.assertEqual(response.status_code, 403)

    # --- parent two-way inbox (the new capability) ---------------------------

    def test_parent_can_open_messages_hub(self):
        """Parents are no longer bounced to Contact School — they get a real inbox."""
        self.client.force_login(self.parent)
        response = self.client.get(reverse("accounts:user_messages"))
        self.assertEqual(response.status_code, 200)

    def test_parent_compose_picker_is_scoped_to_childs_teacher_and_office(self):
        self.client.force_login(self.parent)
        response = self.client.get(reverse("accounts:direct_compose"))
        self.assertEqual(response.status_code, 200)
        recipient_ids = {r["id"] for r in response.context["recipients"]}
        # The child's teacher and the office are offered…
        self.assertIn(self.teacher.id, recipient_ids)
        self.assertIn(self.principal.id, recipient_ids)
        # …but never an unrelated teacher, another parent, or a student.
        self.assertNotIn(self.other_teacher.id, recipient_ids)
        self.assertNotIn(self.other_parent.id, recipient_ids)
        self.assertNotIn(self.student.id, recipient_ids)

    def test_parent_can_message_childs_teacher(self):
        self.client.force_login(self.parent)
        response = self.client.post(
            reverse("accounts:direct_compose"),
            {
                "recipient": str(self.teacher.id),
                "subject": "Homework question",
                "body": "Could you clarify tonight's assignment?",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Message.objects.filter(
                sender=self.parent, recipient=self.teacher
            ).exists()
        )

    def test_parent_cannot_compose_to_another_parent(self):
        self.client.force_login(self.parent)
        count_before = Message.objects.count()
        response = self.client.post(
            reverse("accounts:direct_compose"),
            {
                "recipient": str(self.other_parent.id),
                "subject": "Hi",
                "body": "Trying to reach another parent.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Message.objects.count(), count_before)

    def test_parent_can_open_thread_with_childs_teacher(self):
        self.client.force_login(self.parent)
        response = self.client.get(
            reverse("accounts:direct_thread", args=[self.teacher.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_parent_cannot_open_thread_with_student(self):
        self.client.force_login(self.parent)
        response = self.client.get(
            reverse("accounts:direct_thread", args=[self.student.id])
        )
        self.assertEqual(response.status_code, 403)

    # --- close-the-loop semantics remain intact ------------------------------

    def test_closed_parent_conversation_blocks_parent_reply(self):
        # Staff opens a direct thread with the parent.
        self.client.force_login(self.principal)
        self.client.post(
            reverse("accounts:direct_compose"),
            {
                "recipient": str(self.parent.id),
                "subject": "Finance update",
                "body": "Please upload receipt.",
            },
        )
        # Staff closes the loop.
        close_response = self.client.post(
            reverse("accounts:direct_thread", args=[self.parent.id]),
            {"action": "close"},
        )
        self.assertEqual(close_response.status_code, 302)
        conversation = DirectConversation.get_or_create_for(self.principal, self.parent)
        self.assertIsNotNone(conversation.closed_at)

        # Parent cannot reply into the closed thread.
        count_before = Message.objects.count()
        self.client.force_login(self.parent)
        reply_response = self.client.post(
            reverse("accounts:direct_thread", args=[self.principal.id]),
            {"subject": "Re", "body": "Can you reopen this?"},
        )
        self.assertEqual(reply_response.status_code, 302)
        self.assertEqual(Message.objects.count(), count_before)

    def test_parent_cannot_reopen_closed_conversation_via_compose(self):
        # Staff opens then closes the loop.
        self.client.force_login(self.principal)
        self.client.post(
            reverse("accounts:direct_compose"),
            {"recipient": str(self.parent.id), "subject": "x", "body": "hi"},
        )
        self.client.post(
            reverse("accounts:direct_thread", args=[self.parent.id]),
            {"action": "close"},
        )
        # The parent cannot use "New message" to bypass the close.
        count_before = Message.objects.count()
        self.client.force_login(self.parent)
        response = self.client.post(
            reverse("accounts:direct_compose"),
            {
                "recipient": str(self.principal.id),
                "subject": "Re",
                "body": "Reopening from compose.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Message.objects.count(), count_before)

    # --- hygiene --------------------------------------------------------------

    def test_messages_page_does_not_render_toast_usage_docs(self):
        self.client.force_login(self.principal)
        response = self.client.get(reverse("accounts:user_messages"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Reusable Toast Notification System Usage")
        self.assertNotContains(response, "Include this in base templates, then call")
