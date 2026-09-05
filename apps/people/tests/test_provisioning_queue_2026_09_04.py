"""Guardian approval, and the screen where any of this gets answered.

The guardian case is the one that needed care. A guardian link arrives naming a
student by the BOX's record number, and that number does not name the same child
on the cloud -- a box-created student is assigned a fresh pk up here. So the
resolution is not done in code: approval REQUIRES its caller to name the student,
and the queue shows a candidate for a person to confirm. These tests hold that
line, because the failure it prevents is attaching a guardian to a stranger's
child, which nothing downstream would ever flag as wrong.
"""

from django.test import TestCase
from django.urls import reverse

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.accounts.models import User
from apps.people.models import StudentGuardian, StudentProfile
from apps.people.models_provisioning import ProvisioningRequest
from apps.people.provisioning_service import (
    approve_provisioning_request,
    record_refused_insert,
)
from apps.schools.models import School
from apps.test_utils.http_clients import login_tenant_admin_client
from apps.test_utils.rbac_seed import seed_support_staff_catalog
from apps.test_utils.tenant_hosts import host_routed, tenant_host

PASSWORD = "provisioning-queue-pw"


class _SchoolWithAStudent(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_support_staff_catalog()
        cls.school = School.objects.create(
            name="Guardian School",
            slug="guardian-school",
            subdomain="guardian-school",
            is_active=True,
            country_code="CM",
        )
        cls.other = School.objects.create(
            name="Elsewhere School",
            slug="elsewhere-school",
            subdomain="elsewhere-school",
            is_active=True,
            country_code="CM",
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school, name="2026", start_date="2026-01-01", end_date="2026-12-31"
        )
        cls.dept = Department.objects.create(school=cls.school, name="Trades", code="TR")
        cls.spec = Specialty.objects.create(
            school=cls.school, name="Plumbing", code="PL", department=cls.dept
        )
        cls.classroom = Classroom.objects.create(
            school=cls.school, name="F1", code="F1",
            academic_year=cls.year, department=cls.dept,
        )
        cls.child = StudentProfile.objects.create(
            school=cls.school, first_name="Ada", last_name="Child",
            academic_year=cls.year, specialty=cls.spec, classroom=cls.classroom,
            admission_number="ADM-CHILD-1",
        )
        cls.foreign_child = StudentProfile.objects.create(
            school=cls.other, first_name="Other", last_name="Child",
            admission_number="ADM-OTHER-1",
        )
        cls.actor = User.objects.create_user(
            username="guardian.approver", password=PASSWORD, role=User.Role.ADMIN
        )

    def _request(self, **payload):
        base = {"first_name": "Mary", "last_name": "Parent", "relationship": "Mother"}
        base.update(payload)
        return ProvisioningRequest.objects.create(
            school=self.school,
            entity_type="student_guardian",
            client_offline_id="box-guardian-77",
            payload=base,
        )


class GuardianApprovalNamesTheChildTests(_SchoolWithAStudent):
    def test_approval_without_a_student_is_refused(self):
        row = self._request()
        with self.assertRaises(ValueError) as ctx:
            approve_provisioning_request(row, actor=self.actor)
        self.assertIn("student", str(ctx.exception).lower())
        self.assertFalse(StudentGuardian.objects.exists())

    def test_the_candidate_is_recorded_but_never_used_as_the_answer(self):
        """A suggestion on a screen, not an input to the write."""
        record_refused_insert(
            school_id=self.school.pk,
            entity_type="student_guardian",
            client_offline_id="box-guardian-88",
            values={"first_name": "Mary", "student_id": self.child.pk},
        )
        row = ProvisioningRequest.objects.get(client_offline_id="box-guardian-88")
        self.assertEqual(row.payload["student_candidate_pk"], self.child.pk)
        self.assertIn("Confirm", row.payload["student_candidate_note"])
        # And approval still will not act on it by itself.
        with self.assertRaises(ValueError):
            approve_provisioning_request(row, actor=self.actor)

    def test_a_candidate_that_does_not_exist_says_so(self):
        record_refused_insert(
            school_id=self.school.pk,
            entity_type="student_guardian",
            client_offline_id="box-guardian-99",
            values={"first_name": "Mary", "student_id": 9_000_123},
        )
        row = ProvisioningRequest.objects.get(client_offline_id="box-guardian-99")
        self.assertNotIn("student_candidate_pk", row.payload)
        self.assertIn("does not exist", row.payload["student_candidate_note"])

    def test_approval_with_a_named_student_creates_the_link(self):
        row = self._request()
        link = approve_provisioning_request(
            row, actor=self.actor, student_id=self.child.pk
        )
        self.assertEqual(link.student, self.child)
        self.assertEqual(link.school, self.school)
        self.assertEqual(link.client_offline_id, "box-guardian-77")
        self.assertEqual(link.relationship, "Mother")

    def test_the_guardian_account_cannot_sign_in_and_holds_no_authorisation(self):
        row = self._request()
        link = approve_provisioning_request(
            row, actor=self.actor, student_id=self.child.pk
        )
        self.assertFalse(link.guardian_user.has_usable_password())
        self.assertEqual(link.guardian_user.role, User.Role.PARENT)
        # can_view_finance / can_view_results ride DOWN-ONLY on the rail:
        # authorisation is the cloud's to grant, never a box's to request.
        self.assertFalse(link.can_view_finance)
        self.assertFalse(link.can_view_results)

    def test_a_student_from_another_school_is_refused(self):
        row = self._request()
        with self.assertRaises(ValueError) as ctx:
            approve_provisioning_request(
                row, actor=self.actor, student_id=self.foreign_child.pk
            )
        self.assertIn("not in this school", str(ctx.exception))
        self.assertFalse(StudentGuardian.objects.exists())
        row.refresh_from_db()
        self.assertEqual(row.status, ProvisioningRequest.Status.PENDING)


@host_routed
class ProvisioningQueueScreenTests(_SchoolWithAStudent):
    def setUp(self):
        self.host = tenant_host(self.school)
        self.client = login_tenant_admin_client(
            self.actor, password=PASSWORD, host=self.host, school=self.school
        )

    def _pending_teacher(self, coid="box-t-1"):
        return ProvisioningRequest.objects.create(
            school=self.school,
            entity_type="teacher",
            client_offline_id=coid,
            payload={"first_name": "Ada", "last_name": "Nkeng", "staff_id": "EMP-1"},
            requested_role="DRIVER",
            times_seen=687,
        )

    def test_the_queue_renders(self):
        self._pending_teacher()
        res = self.client.get(
            reverse("accounts:provisioning_queue"), HTTP_HOST=self.host
        )
        self.assertEqual(res.status_code, 200, res.get("Location", ""))
        html = res.content.decode("utf-8")
        self.assertIn("Nkeng", html)
        self.assertIn("687", html, "the count is what makes someone act")

    def test_approving_from_the_screen_creates_the_person(self):
        row = self._pending_teacher()
        res = self.client.post(
            reverse("accounts:provisioning_approve", args=[row.pk]),
            {"role": "DRIVER"},
            HTTP_HOST=self.host,
        )
        self.assertEqual(res.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.status, ProvisioningRequest.Status.APPROVED)
        self.assertIsNotNone(row.created_user)
        self.assertEqual(row.created_user.role, User.Role.DRIVER)

    def test_declining_from_the_screen_records_the_reason(self):
        row = self._pending_teacher()
        self.client.post(
            reverse("accounts:provisioning_decline", args=[row.pk]),
            {"reason": "Left in July."},
            HTTP_HOST=self.host,
        )
        row.refresh_from_db()
        self.assertEqual(row.status, ProvisioningRequest.Status.DECLINED)
        self.assertEqual(row.decline_reason, "Left in July.")

    def test_another_schools_request_is_not_reachable_by_number(self):
        foreign = ProvisioningRequest.objects.create(
            school=self.other,
            entity_type="teacher",
            client_offline_id="box-foreign",
            payload={"first_name": "Not", "last_name": "Yours"},
        )
        res = self.client.post(
            reverse("accounts:provisioning_approve", args=[foreign.pk]),
            {"role": "TEACHER"},
            HTTP_HOST=self.host,
        )
        self.assertEqual(res.status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, ProvisioningRequest.Status.PENDING)

    def test_a_get_cannot_approve(self):
        row = self._pending_teacher()
        res = self.client.get(
            reverse("accounts:provisioning_approve", args=[row.pk]), HTTP_HOST=self.host
        )
        self.assertEqual(res.status_code, 405)
        row.refresh_from_db()
        self.assertEqual(row.status, ProvisioningRequest.Status.PENDING)
