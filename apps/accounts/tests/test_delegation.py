"""Tests for delegation (Out of Office / Acting) helpers and models."""

from django.test import TestCase
from django.urls import resolve, reverse
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import User, Delegation
from apps.accounts.permissions import can_access_module
from apps.accounts.delegation import (
    get_approval_roles_for_workflow,
    get_effective_approvers,
    WORKFLOW_SYLLABUS_APPROVAL,
    WORKFLOW_GRADE_APPROVAL,
    can_user_approve_for_workflow,
    get_active_delegation_for_delegate,
)
from apps.platform_runtime.helpers import get_platform_site_settings_record


class DelegationHelperTests(TestCase):
    def setUp(self):
        self.site = get_platform_site_settings_record(create=True)
        self.site.syllabus_approval_roles = ["DEAN", "HOD"]
        self.site.grade_approval_roles = ["DEAN", "HOD"]
        self.site.save()

        self.dean = User.objects.create_user(
            "dean", "dean@test.com", "pass", role=User.Role.DEAN
        )
        self.hod = User.objects.create_user(
            "hod", "hod@test.com", "pass", role=User.Role.HOD
        )
        self.teacher = User.objects.create_user(
            "teacher", "teacher@test.com", "pass", role=User.Role.TEACHER
        )

    def test_get_approval_roles_for_workflow(self):
        roles = get_approval_roles_for_workflow(WORKFLOW_SYLLABUS_APPROVAL)
        self.assertIn("DEAN", roles)
        self.assertIn("HOD", roles)
        roles_grade = get_approval_roles_for_workflow(WORKFLOW_GRADE_APPROVAL)
        self.assertIn("DEAN", roles_grade)

    def test_get_effective_approvers_without_delegation(self):
        approvers = get_effective_approvers(WORKFLOW_SYLLABUS_APPROVAL)
        ids = [u.id for u in approvers]
        self.assertIn(self.dean.id, ids)
        self.assertIn(self.hod.id, ids)
        self.assertNotIn(self.teacher.id, ids)

    def test_can_user_approve_for_workflow(self):
        self.assertTrue(
            can_user_approve_for_workflow(self.dean, WORKFLOW_SYLLABUS_APPROVAL)
        )
        self.assertTrue(
            can_user_approve_for_workflow(self.hod, WORKFLOW_SYLLABUS_APPROVAL)
        )
        self.assertFalse(
            can_user_approve_for_workflow(self.teacher, WORKFLOW_SYLLABUS_APPROVAL)
        )

    def test_get_effective_approvers_with_delegation(self):
        """When Dean is OOO and delegated to Teacher, Teacher should be an effective approver."""
        now = timezone.now()
        Delegation.objects.create(
            delegator=self.dean,
            delegate=self.teacher,
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=5),
            is_active=True,
            scope=[WORKFLOW_SYLLABUS_APPROVAL],
        )
        approvers = get_effective_approvers(WORKFLOW_SYLLABUS_APPROVAL)
        ids = [u.id for u in approvers]
        self.assertIn(self.dean.id, ids)
        self.assertIn(self.hod.id, ids)
        self.assertIn(self.teacher.id, ids)

    def test_get_active_delegation_for_delegate(self):
        now = timezone.now()
        d = Delegation.objects.create(
            delegator=self.dean,
            delegate=self.teacher,
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=5),
            is_active=True,
        )
        active = get_active_delegation_for_delegate(self.teacher)
        self.assertIsNotNone(active)
        self.assertEqual(active.id, d.id)
        self.assertIsNone(get_active_delegation_for_delegate(self.dean))

    def test_delegation_portal_urls_resolve_to_accounts_namespace_for_module_middleware(self):
        """Drift guard: profile/delegation routes must stay under ``accounts`` so ``MODULE_ACCESS_DEFAULTS['accounts']`` applies."""
        for name in (
            "accounts:my_delegations",
            "accounts:delegation_add",
            "accounts:delegation_catch_up",
        ):
            path = reverse(name)
            match = resolve(path)
            self.assertEqual(
                match.namespace,
                "accounts",
                msg=f"{name} must resolve to accounts namespace (got {match.namespace!r})",
            )
        teacher = User.objects.create_user(
            "tmw", "tmw@test.com", "pass", role=User.Role.TEACHER
        )
        self.assertTrue(can_access_module(teacher, "accounts", action="read"))
        self.assertTrue(can_access_module(teacher, "accounts", action="write"))
