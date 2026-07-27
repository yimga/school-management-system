"""The LIVE SCHOOL ACTIVITY ticker (enrollment / payments / operational events) is
an ADMIN-TIER header surface. Parents, teachers, students and general staff must
NOT receive it in the header ticker / landing strip / drawer — the cockpit context
flips ``tenant_activity_ticker.enabled`` off for any non-admin chrome role cluster,
so all three render surfaces suppress together off one decision.
"""

from __future__ import annotations

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.siteconfig.cockpit_context import cockpit_context


class ActivityTickerRbacGateTests(TestCase):
    def _ctx_for(self, role):
        user = User.objects.create_user(
            username=f"tick-{role.lower()}",
            email=f"tick-{role.lower()}@example.com",
            password="Test1234!",
            role=role,
        )
        request = RequestFactory().get("/portal/")
        request.user = user
        request.session = {}
        request.public_host_kind = "tenant"
        return cockpit_context(request)

    def _ticker_enabled(self, ctx):
        return bool(
            ((ctx.get("cockpit") or {}).get("tenant_activity_ticker") or {}).get("enabled")
        )

    def test_school_admin_keeps_the_live_activity_ticker(self):
        ctx = self._ctx_for(User.Role.ADMIN)
        self.assertTrue(self._ticker_enabled(ctx))

    def test_parent_does_not_get_the_live_activity_ticker(self):
        ctx = self._ctx_for(User.Role.PARENT)
        self.assertFalse(self._ticker_enabled(ctx))

    def test_teacher_does_not_get_the_live_activity_ticker(self):
        ctx = self._ctx_for(User.Role.TEACHER)
        self.assertFalse(self._ticker_enabled(ctx))

    def test_student_does_not_get_the_live_activity_ticker(self):
        ctx = self._ctx_for(User.Role.STUDENT)
        self.assertFalse(self._ticker_enabled(ctx))
