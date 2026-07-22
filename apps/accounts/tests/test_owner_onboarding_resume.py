"""_owner_onboarding_resume_name: resume the wizard on login, but never trap.

Locks the post-login resume helper: it routes an owner back into the guided
onboarding wizard only when that owner STARTED but did not COMPLETE it, and is a
no-op for established owners (empty state), non-owners, suspended owners, and a
missing tenant school — so it can never loop or block sign-in.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.views import _owner_onboarding_resume_name
from apps.schools.models import School, SchoolMembership


class OwnerOnboardingResumeTests(TestCase):
    def setUp(self):
        slug = f"g-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name="Gilead", slug=slug, subdomain=slug, is_active=True
        )
        self.owner = self._user()
        SchoolMembership.objects.create(
            user=self.owner, school=self.school, role=User.Role.ADMIN,
            is_primary=True, is_school_owner=True,
        )

    def _user(self):
        return User.objects.create_user(
            username=f"u-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex[:8]}@example.com",
            password="pass12345678", role=User.Role.ADMIN,
        )

    def _req(self):
        return SimpleNamespace(school=self.school)

    def _set_state(self, **kw):
        self.school.settings = {"owner_onboarding": kw}
        self.school.save(update_fields=["settings"])

    def test_incomplete_school_step_resumes_school(self):
        self._set_state(step="school", completed=False)
        self.assertEqual(
            _owner_onboarding_resume_name(self._req(), self.owner),
            "accounts:owner_onboarding_school",
        )

    def test_done_step_resumes_done(self):
        self._set_state(step="done", completed=False)
        self.assertEqual(
            _owner_onboarding_resume_name(self._req(), self.owner),
            "accounts:owner_onboarding_done",
        )

    def test_mfa_step_resumes_mfa(self):
        self._set_state(step="mfa", completed=False)
        self.assertEqual(
            _owner_onboarding_resume_name(self._req(), self.owner),
            "accounts:owner_onboarding_mfa",
        )

    def test_completed_returns_none(self):
        self._set_state(step="done", completed=True)
        self.assertIsNone(_owner_onboarding_resume_name(self._req(), self.owner))

    def test_never_started_returns_none(self):
        # Established owner with no wizard state must NOT be force-routed.
        self.assertIsNone(_owner_onboarding_resume_name(self._req(), self.owner))

    def test_non_owner_returns_none(self):
        member = self._user()
        SchoolMembership.objects.create(
            user=member, school=self.school, role=User.Role.TEACHER,
            is_school_owner=False,
        )
        self._set_state(step="school", completed=False)
        self.assertIsNone(_owner_onboarding_resume_name(self._req(), member))

    def test_suspended_owner_returns_none(self):
        SchoolMembership.objects.filter(user=self.owner, school=self.school).update(
            suspended_at=timezone.now()
        )
        self._set_state(step="school", completed=False)
        self.assertIsNone(_owner_onboarding_resume_name(self._req(), self.owner))

    def test_no_tenant_school_returns_none(self):
        self._set_state(step="school", completed=False)
        self.assertIsNone(
            _owner_onboarding_resume_name(SimpleNamespace(school=None), self.owner)
        )
