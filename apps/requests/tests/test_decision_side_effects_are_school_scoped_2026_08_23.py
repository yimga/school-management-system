"""Approving a request must not reach outside the request's school.

``apply_request_decision`` is the single chokepoint where an approval becomes a
real grant in another app. Three of its handlers resolved the row to write by
``target_object_id`` alone, and a fourth updated every guardian link the
requester holds:

  * ``_apply_grade_approval`` / ``_apply_leave_approval`` / ``_apply_report_request``
    did ``Model.objects.filter(id=request.target_object_id).first()``. That field
    is a plain CharField -- ``create_access_request(target=...)`` takes it from any
    caller and ``AccessRequestAdmin`` leaves it editable -- so School A's decision
    landed on School B's row.
  * ``_apply_finance_access`` filtered guardian links by ``guardian_user`` only.
    ``details["student_ids"]`` is EMPTY for every request that
    ``finance/offline_workflow_handlers.py`` creates without a named student, and
    the empty case is the ``update every link`` case: one school's approval turned
    on finance visibility at every school the guardian belongs to.
  * ``_apply_module_access`` called ``feature_permissions.add(perm)`` with no
    ``FeaturePermissionScope`` row. The ABSENCE of that row means the historical
    PLATFORM-WIDE grant (accounts/models.py::_direct_grant_reaches), so the code
    was held at every school the requester belongs to.

Every test here fails on the pre-fix tree.
"""

from __future__ import annotations

import uuid

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from apps.accounts.models import FeaturePermissionScope, Permission, User
from apps.people.models import StudentGuardian, StudentProfile, TeacherLeaveRequest, TeacherProfile
from apps.requests.models import AccessRequest, RequestDecision
from apps.requests.services import apply_request_decision
from apps.schools.models import School, SchoolMembership


class _TwoSchools(TestCase):
    def setUp(self) -> None:
        uid = uuid.uuid4().hex[:8]
        self.uid = uid
        self.school_a = School.objects.create(
            name=f"Scope A {uid}", slug=f"scope-a-{uid}", subdomain=f"scopea{uid}",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name=f"Scope B {uid}", slug=f"scope-b-{uid}", subdomain=f"scopeb{uid}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"scope_adm_{uid}", password="Test1234", role=User.Role.ADMIN
        )

    def _decide(self, req, decision=RequestDecision.Decision.APPROVED, reason=""):
        return apply_request_decision(
            request=req, decision=decision, reason=reason, actor=self.admin
        )


class FinanceAccessStaysInsideTheRequestSchoolTests(_TwoSchools):
    def setUp(self) -> None:
        super().setUp()
        self.guardian = User.objects.create_user(
            username=f"scope_gdn_{self.uid}", password="Test1234", role=User.Role.PARENT
        )
        self.student_a = StudentProfile.objects.create(
            school=self.school_a, first_name="Ada", last_name="A",
            student_code=f"SA-{self.uid}",
        )
        self.student_b = StudentProfile.objects.create(
            school=self.school_b, first_name="Bo", last_name="B",
            student_code=f"SB-{self.uid}",
        )
        self.link_a = StudentGuardian.objects.create(
            guardian_user=self.guardian, student=self.student_a, can_view_finance=False
        )
        self.link_b = StudentGuardian.objects.create(
            guardian_user=self.guardian, student=self.student_b, can_view_finance=False
        )

    def _finance_request(self, details=None):
        return AccessRequest.objects.create(
            request_type=AccessRequest.RequestType.FINANCE_ACCESS,
            status=AccessRequest.Status.PENDING,
            school=self.school_a,
            requester=self.guardian,
            details=details or {},
        )

    def test_an_empty_student_id_list_does_not_reach_the_other_school(self) -> None:
        self._decide(self._finance_request())
        self.link_b.refresh_from_db()
        self.assertFalse(
            self.link_b.can_view_finance,
            "School A's approval granted finance visibility at School B",
        )

    def test_the_requesting_school_link_is_still_granted(self) -> None:
        """The fix must not break the grant it narrows."""
        self._decide(self._finance_request())
        self.link_a.refresh_from_db()
        self.assertTrue(self.link_a.can_view_finance)

    def test_an_explicit_foreign_student_id_is_still_refused(self) -> None:
        self._decide(self._finance_request({"student_ids": [self.student_b.pk]}))
        self.link_b.refresh_from_db()
        self.assertFalse(self.link_b.can_view_finance)


class LeaveApprovalStaysInsideTheRequestSchoolTests(_TwoSchools):
    def setUp(self) -> None:
        super().setUp()
        teacher_user = User.objects.create_user(
            username=f"scope_tch_{self.uid}", password="Test1234", role=User.Role.TEACHER
        )
        self.teacher_b = TeacherProfile.objects.create(
            school=self.school_b, user=teacher_user
        )
        self.leave_b = TeacherLeaveRequest.objects.create(
            teacher=self.teacher_b,
            start_date="2026-09-01",
            end_date="2026-09-03",
            status=TeacherLeaveRequest.Status.PENDING,
        )
        # The post_save mirror in signals.py makes its own AccessRequest; it
        # resolves no school (TeacherLeaveRequest has no `.school`), so it cannot
        # stand in for the School A row this test needs.
        AccessRequest.objects.all().delete()

    def _leave_request_owned_by(self, school):
        return AccessRequest.objects.create(
            request_type=AccessRequest.RequestType.LEAVE_APPROVAL,
            status=AccessRequest.Status.PENDING,
            school=school,
            target_content_type=ContentType.objects.get_for_model(TeacherLeaveRequest),
            target_object_id=str(self.leave_b.pk),
        )

    def test_another_schools_leave_request_is_not_decided(self) -> None:
        self._decide(self._leave_request_owned_by(self.school_a))
        self.leave_b.refresh_from_db()
        self.assertEqual(
            self.leave_b.status,
            TeacherLeaveRequest.Status.PENDING,
            "School A approved a leave request belonging to School B",
        )

    def test_the_owning_school_can_still_decide_it(self) -> None:
        """Control: the scoping must not break the handler it guards."""
        self._decide(self._leave_request_owned_by(self.school_b))
        self.leave_b.refresh_from_db()
        self.assertEqual(self.leave_b.status, TeacherLeaveRequest.Status.APPROVED)

    def test_a_target_of_the_wrong_model_is_ignored(self) -> None:
        """The handler is dispatched on request_type; the pk alone cannot tell
        an integer-pk leave request from an integer-pk report request."""
        req = self._leave_request_owned_by(self.school_b)
        req.target_content_type = ContentType.objects.get_for_model(School)
        req.save(update_fields=["target_content_type"])
        self._decide(req)
        self.leave_b.refresh_from_db()
        self.assertEqual(self.leave_b.status, TeacherLeaveRequest.Status.PENDING)


class ModuleAccessGrantIsScopedToTheApprovingSchoolTests(_TwoSchools):
    CODE = "module.finance.read"

    def setUp(self) -> None:
        super().setUp()
        self.requester = User.objects.create_user(
            username=f"scope_mod_{self.uid}", password="Test1234", role=User.Role.TEACHER
        )
        for school in (self.school_a, self.school_b):
            SchoolMembership.objects.create(
                user=self.requester, school=school, role=User.Role.TEACHER
            )

    def _module_request(self, module="finance", action="read", school=None):
        return AccessRequest.objects.create(
            request_type=AccessRequest.RequestType.MODULE_ACCESS,
            status=AccessRequest.Status.PENDING,
            school=school or self.school_a,
            requester=self.requester,
            details={"module": module, "action": action},
        )

    def test_the_grant_carries_a_scope_row_for_the_approving_school(self) -> None:
        self._decide(self._module_request())
        self.assertTrue(
            FeaturePermissionScope.objects.filter(
                user=self.requester,
                permission__code=self.CODE,
                school=self.school_a,
            ).exists(),
            "no FeaturePermissionScope row: the grant is platform-wide",
        )

    def test_the_grant_does_not_reach_the_other_school(self) -> None:
        self._decide(self._module_request())
        self.requester.refresh_from_db()
        self.assertFalse(
            self.requester.has_feature_permission(self.CODE, school=self.school_b),
            "School A's approval granted the module code at School B",
        )

    def test_the_grant_still_holds_at_the_approving_school(self) -> None:
        self._decide(self._module_request())
        self.requester.refresh_from_db()
        self.assertTrue(
            self.requester.has_feature_permission(self.CODE, school=self.school_a)
        )

    def test_an_existing_platform_wide_grant_is_not_narrowed(self) -> None:
        """A code held before scoping existed keeps the meaning it was written
        with -- this surface did not issue it and must not revoke it."""
        perm = Permission.objects.create(code=self.CODE, name="Finance Read Access")
        self.requester.feature_permissions.add(perm)
        self._decide(self._module_request())
        self.requester.refresh_from_db()
        self.assertTrue(
            self.requester.has_feature_permission(self.CODE, school=self.school_b)
        )

    def test_an_oversized_module_name_mints_no_permission(self) -> None:
        """`module` is a free-text POST field and Permission.code is
        varchar(120) UNIQUE -- an over-long code is a DataError inside the
        atomic decision block, which 500s the approver and rolls the batch back."""
        module = "x" * 200
        req = self._module_request(module=module)
        self._decide(req)
        self.assertFalse(
            Permission.objects.filter(code=f"module.{module}.read").exists(),
            "an unbounded module name minted a permission code",
        )
        req.refresh_from_db()
        self.assertEqual(req.status, AccessRequest.Status.APPROVED)
        self.assertTrue(
            req.audits.filter(action="module_access_rejected").exists(),
            "the refused grant left no trail",
        )
