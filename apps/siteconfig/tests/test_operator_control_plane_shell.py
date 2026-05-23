"""Manager-host siteconfig operator pages use control_plane_base shell."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from apps.test_utils.http_clients import MANAGER_TEST_DEFAULTS, login_manager_client

_MGR = "manager.runmycampus.com"


@override_settings(
    **MANAGER_TEST_DEFAULTS,
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _MGR, "*"],
)
class OperatorControlPlaneShellTests(TransactionTestCase):
    databases = {"default"}

    def setUp(self):
        User = get_user_model()
        suffix = uuid.uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"cp_shell_op_{suffix}",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        self.client = login_manager_client(self.user, password="x" * 8)

    def _assert_cp_shell(self, path_name: str):
        path = reverse(path_name)
        resp = self.client.get(path)
        self.assertEqual(
            resp.status_code,
            200,
            msg=f"{path} -> {resp.status_code} {resp.get('Location', '')!r} "
            f"{getattr(resp, 'content', b'')[:200]!r}",
        )
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-os-shell="control-plane"', body)
        self.assertIn('id="cp-main-content"', body)
        self.assertIn('meta name="csrf-token"', body)

    def test_ai_center_manager_shell(self):
        self._assert_cp_shell("siteconfig:ai_center")

    def test_ai_governance_manager_shell(self):
        self._assert_cp_shell("siteconfig:ai_governance")

    def test_console_domains_hub_manager_shell(self):
        self._assert_cp_shell("siteconfig:console_domains_hub")

    def test_dashboard_configuration_hub_manager_shell(self):
        from apps.siteconfig.models import Plan
        from apps.schools.models import School

        plan = Plan.objects.create(name="Free", slug="basic", is_active=True)
        school = School.objects.create(
            name="Dash Config School",
            slug="dashcfg",
            subdomain="dashcfg",
            is_active=True,
            plan=plan,
        )
        session = self.client.session
        session["school_id"] = str(school.id)
        session.save()
        self._assert_cp_shell("siteconfig:dashboard_configuration_hub")

    def test_feature_control_audit_manager_shell(self):
        from apps.accounts.models import Permission

        perm, _ = Permission.objects.get_or_create(
            code="settings.feature_control",
            defaults={"name": "Feature control"},
        )
        self.user.feature_permissions.add(perm)
        self._assert_cp_shell("siteconfig:feature_control_audit")
