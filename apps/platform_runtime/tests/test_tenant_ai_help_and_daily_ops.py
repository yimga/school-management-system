"""Tenant AI help and daily ops tests."""

from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.platform_runtime.tenant_ai_help import (
    build_tenant_ai_help_context,
    offline_help_actions,
)
from apps.platform_runtime.tenant_daily_ops import (
    next_best_actions_for_role,
    resolve_action_urls,
)
from apps.schools.models import School


class TenantAIHelpTests(SimpleTestCase):
    def test_offline_actions_non_destructive(self):
        actions = offline_help_actions()
        self.assertTrue(actions)
        self.assertTrue(all("action" in a for a in actions))

    def test_help_context_no_raw_pii_keys(self):
        factory = RequestFactory()
        request = factory.get("/portal/")
        request.school = None
        request.user = type("U", (), {"is_authenticated": False})()
        ctx = build_tenant_ai_help_context(request, route_name="portal:dashboard")
        self.assertIn("tenant_safe_message", ctx)
        self.assertNotIn("email", str(ctx).lower())


class TenantDailyOpsTests(TestCase):
    def test_teacher_next_best_actions(self):
        school = School.objects.create(
            name="Ops",
            slug="ops-school",
            subdomain="ops-school",
            is_active=True,
        )
        user = type("U", (), {"role": "TEACHER"})()
        actions = next_best_actions_for_role(school, user)
        self.assertTrue(actions)
        self.assertEqual(actions[0]["school_id"], str(school.pk))

    def test_admin_workflow_actions_include_attendance(self):
        school = School.objects.create(
            name="Ops2",
            slug="ops2-school",
            subdomain="ops2-school",
            is_active=True,
        )
        user = type("U", (), {"role": "ADMIN"})()
        actions = next_best_actions_for_role(school, user)
        keys = {a["key"] for a in actions}
        self.assertIn("attendance", keys)

    def test_resolve_action_urls_adds_url_field(self):
        school = School.objects.create(
            name="Ops3",
            slug="ops3-school",
            subdomain="ops3-school",
            is_active=True,
        )
        user = type("U", (), {"role": "TEACHER"})()
        resolved = resolve_action_urls(next_best_actions_for_role(school, user))
        self.assertTrue(all("url" in a for a in resolved))
