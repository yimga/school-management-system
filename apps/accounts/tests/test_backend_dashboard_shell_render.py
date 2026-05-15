"""1007B: tenant Client render asserts backend dashboard shell/data markers."""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission as FeaturePermission, User
from apps.schools.models import School

_T_HOST = "bd-shell.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST],
    CONVERSION_LOCK_STRICT=False,
    CONVERSION_LOCK_ALL_SCHOOLS=False,
    DISABLE_SCHOOL_ACTIVATION_GATE=True,
)
class BackendDashboardShellRenderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Backend Shell School",
            slug="bd-shell",
            subdomain="bd-shell",
            is_active=True,
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_T_HOST, raise_request_exception=False)

    def _mark_mfa_verified(self, user):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.update_or_create(
            user=user,
            name="shell-render-test",
            defaults={"confirmed": True},
        )
        session = self.client.session
        session["mfa_verified"] = True
        session.save()

    def test_backend_dashboard_renders_role_ops_and_system_indicators(self):
        u = User.objects.create_user(
            username="bd_shell_adm",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        self.client.login(username="bd_shell_adm", password="x" * 8)
        self._mark_mfa_verified(u)
        path = reverse("accounts:backend_dashboard", urlconf="config.tenant_urls")
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200, msg=getattr(resp, "content", b"")[:500])
        body = resp.content.decode("utf-8", errors="replace")
        # 1045: role-home surface marker (PATH II dashboard depth; complements 1007B/1019+ strips)
        self.assertIn('data-shell-role-home="backend"', body)
        self.assertIn('data-shell-role-ops="backend"', body)
        self.assertIn('data-shell-chrome="backend-system-indicators"', body)
        self.assertIn("data-backend-indicator=", body)
        self.assertIn('data-shell-chrome="backend-ops-strip"', body)
        self.assertIn('data-shell-chrome="backend-operational-status-load"', body)
        self.assertIn('data-shell-chrome="breadcrumb-row"', body)
        self.assertIn('data-shell-ops-section="pending-alerts-activity"', body)
        self.assertIn("data-shell-alerts=", body)
        self.assertIn('data-shell-chrome="backend-audit-snapshot"', body)
        self.assertIn('data-shell-ops-section="audit-system-counts"', body)
        self.assertIn('data-ops-count="pending-invites"', body)
        self.assertIn('data-shell-chrome="backend-stats-core-strip"', body)
        self.assertIn('data-shell-ops-section="core-kpi-counts"', body)
        self.assertIn('data-kpi-count="students-active"', body)
        self.assertIn('data-shell-chrome="backend-finance-pulse-strip"', body)
        self.assertIn('data-shell-ops-section="finance-pulse-counts"', body)
        self.assertIn('data-kpi-count="finance-overdue"', body)
        # 1049: planner recommended-next shared chrome strip (reuses context; no new view logic)
        self.assertIn('data-shell-chrome="backend-planner-recommended-next"', body)
        self.assertIn('data-shell-ops-section="planner-recommended-next"', body)
        # Wave E: planner rail widget markers for product depth / tooling
        self.assertIn('data-backend-widget-surface="planner-rail"', body)
        self.assertIn('data-backend-widget-role="operational-rollup"', body)
        # Operator command center: activation, CSV migration, runtime, catalog
        self.assertIn('data-backend-command-center="setup-strip"', body)
        self.assertIn("data-rmc-operator-setup-strip", body)

    def test_1087_backend_dashboard_includes_token_stylesheet(self):
        """SOT §11.4 batch 1087 — command-center density token contract is linked."""
        u = User.objects.create_user(
            username="bd_1087_tok",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        u.feature_permissions.add(self.perm_settings)
        self.client.login(username="bd_1087_tok", password="x" * 8)
        self._mark_mfa_verified(u)
        path = reverse("accounts:backend_dashboard", urlconf="config.tenant_urls")
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        # Single token file for --dash-gap, --dash-card-pad, section spacing (see backend-dashboard-tokens.css)
        self.assertIn("backend-dashboard-tokens.css", body)
