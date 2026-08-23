"""Approver resolution must not import another tenant's staff.

``get_users_with_roles(role_codes)`` returned
``User.objects.filter(Q(role__in=...) | Q(roles__code__in=...))`` with no school
filter at all. ``get_effective_approvers(workflow_key, school=school)`` accepts a
school but used it only to look up WHICH role codes approve -- the resulting user
set was platform-wide.

That set flows verbatim into ``siteconfig.workflow_resolver.get_approval_workflow``
-> ``approver_ids``, which is the SOLE authorization check in
``syllabus_approval_queue``, ``syllabus_approve`` and ``syllabus_preview``
(apps/academics/views_syllabus.py).

So a user who is a plain TEACHER at School A, and additionally holds a DEAN
AccessRole scoped to School B, passed School A's membership middleware as a
teacher, matched ``roles__code__in=["DEAN"]`` on the School-B row, and could list
and approve School A's syllabi. Multi-school accounts are a supported state
(migration 0046, UserTenantBinding), so this is reachable, not hypothetical.

``school=None`` stays deliberately unscoped -- that is the platform-wide call
shape ``test_delegation.py`` exercises, and narrowing it would change an
unrelated contract.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.accounts.delegation import (
    WORKFLOW_SYLLABUS_APPROVAL,
    can_user_approve_for_workflow,
    get_effective_approvers,
    get_users_with_roles,
)
from apps.accounts.models import AccessRole, User
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.schools.models import School, SchoolMembership


class ApproverResolutionIsSchoolScopedTests(TestCase):
    def setUp(self) -> None:
        site = get_platform_site_settings_record(create=True)
        site.apply_feature_control_state(
            field_updates={"syllabus_approval_roles": ["DEAN", "HOD"]},
        )
        tag = uuid.uuid4().hex[:8]
        self.school_a = School.objects.create(
            name="Approve A",
            slug=f"apa-{tag}",
            subdomain=f"apa-{tag}",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="Approve B",
            slug=f"apb-{tag}",
            subdomain=f"apb-{tag}",
            is_active=True,
        )
        self.dean_role_a = AccessRole.objects.create(
            code="DEAN", name="Dean of A", school=self.school_a
        )
        self.dean_role_b = AccessRole.objects.create(
            code="DEAN", name="Dean of B", school=self.school_b
        )

        # Legitimate approver AT school A. This is the guard against a vacuous
        # pass: if the approval roles failed to resolve, or the membership filter
        # were too tight, the "outsider excluded" assertions would pass against an
        # empty set and measure nothing.
        self.insider = self._member("insider", tag, self.school_a)
        self.insider.roles.add(self.dean_role_a)

        # Teacher at A who holds a DEAN role scoped to B. The attack.
        self.crosser = self._member("crosser", tag, self.school_a)
        self.crosser.roles.add(self.dean_role_b)

        # Primary-role DEAN whose only membership is at B — the ``role`` field is
        # a platform column, so this leg leaked too.
        self.outsider = self._member(
            "outsider", tag, self.school_b, role=User.Role.DEAN
        )

    def _member(self, name, tag, school, role=User.Role.TEACHER):
        user = User.objects.create_user(
            username=f"{name}-{tag}",
            email=f"{name}-{tag}@example.com",
            password="pass12345678",
            role=role,
        )
        SchoolMembership.objects.create(user=user, school=school, role=role)
        return user

    def _approver_ids(self, school):
        return {u.pk for u in get_effective_approvers(WORKFLOW_SYLLABUS_APPROVAL, school=school)}

    def test_a_legitimate_approver_is_still_resolved(self) -> None:
        self.assertIn(self.insider.pk, self._approver_ids(self.school_a))

    def test_a_role_scoped_to_another_school_does_not_approve_here(self) -> None:
        self.assertNotIn(self.crosser.pk, self._approver_ids(self.school_a))

    def test_a_primary_role_at_another_school_does_not_approve_here(self) -> None:
        self.assertNotIn(self.outsider.pk, self._approver_ids(self.school_a))

    def test_the_view_gate_reads_the_scoped_set(self) -> None:
        """``approver_ids`` is the whole authorization check on the syllabus views."""
        from apps.siteconfig.workflow_resolver import get_approval_workflow

        wf = get_approval_workflow(self.school_a, WORKFLOW_SYLLABUS_APPROVAL)
        ids = wf.get("approver_ids") or []
        self.assertIn(self.insider.pk, ids)
        self.assertNotIn(self.crosser.pk, ids)
        self.assertNotIn(self.outsider.pk, ids)

    def test_can_user_approve_for_workflow_agrees(self) -> None:
        self.assertTrue(
            can_user_approve_for_workflow(
                self.insider, WORKFLOW_SYLLABUS_APPROVAL, school=self.school_a
            )
        )
        self.assertFalse(
            can_user_approve_for_workflow(
                self.crosser, WORKFLOW_SYLLABUS_APPROVAL, school=self.school_a
            )
        )

    def test_a_suspended_member_is_not_an_approver(self) -> None:
        from django.utils import timezone

        SchoolMembership.objects.filter(
            user=self.insider, school=self.school_a
        ).update(suspended_at=timezone.now())
        self.assertNotIn(self.insider.pk, self._approver_ids(self.school_a))

    def test_school_none_stays_platform_wide(self) -> None:
        """The unscoped call shape is a separate contract (test_delegation.py)."""
        ids = set(get_users_with_roles(["DEAN"]).values_list("pk", flat=True))
        self.assertIn(self.crosser.pk, ids)
        self.assertIn(self.outsider.pk, ids)

    def test_a_global_template_role_still_approves_everywhere(self) -> None:
        """A ``school IS NULL`` AccessRole applies at every school by design."""
        global_hod, _ = AccessRole.objects.get_or_create(
            code="HOD", school=None, defaults={"name": "Head of Department"}
        )
        self.insider.roles.clear()
        self.insider.roles.add(global_hod)
        self.assertIn(self.insider.pk, self._approver_ids(self.school_a))
