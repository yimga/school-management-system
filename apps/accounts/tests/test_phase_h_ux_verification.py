"""
Phase H — Full codebase and live UX verification.

RUNMYCAMPUS §11 Phase H: Ensure all links, buttons, shortcuts resolve; all dashboards/pages
work (no 404/500 on valid routes); error handlers render correctly.

CI / no-DB slice: bash scripts/run_phase_h_verification.sh
  (runs smoke_urls + PhaseHUrlReverseTests + phase_h_audit static + --live)
Full module (requires DB): python manage.py test apps.accounts.tests.test_phase_h_ux_verification
"""

from django.test import SimpleTestCase, TestCase, Client, override_settings
from django.urls import reverse
from django.http import HttpRequest


# Paths that must resolve and return acceptable status (200, 301, 302, 403 — not 404, 500).
# (path, allowed_statuses). Use HTTP_HOST to switch manager vs tenant.
MANAGER_CRITICAL_PATHS = [
    ("/", (200, 302)),
    ("/super/", (200, 302)),
    ("/admin/", (200, 302)),
    ("/authentication/login/", (200,)),
    ("/studio/experience/", (200, 302)),
    ("/studio/automation/", (200, 302)),
    ("/studio/control/", (200, 302)),
    ("/health/", (200,)),
    ("/healthz/", (200,)),
    ("/api/health/", (200,)),
    ("/siteconfig/preferences/", (200, 302)),
    ("/siteconfig/console/", (200, 302)),
]

TENANT_CRITICAL_PATHS = [
    ("/", (200, 301, 302)),
    ("/health/", (200,)),
    ("/healthz/", (200,)),
    ("/admin/", (200, 302)),
    ("/authentication/login/", (200,)),
    ("/authentication/backend/", (200, 302)),
    ("/portal/parent/", (200, 302)),
    ("/finance/", (200, 302)),
    ("/analytics/", (200, 302)),
    ("/compliance/dashboard/", (200, 302)),
    ("/evals/teacher/", (200, 302)),
    ("/payroll/", (200, 302)),
    ("/automation/outcomes/", (200, 302)),
    ("/communication/groups/", (200, 302)),
    ("/requests/", (200, 302)),
    ("/academics/teacher/syllabi/", (200, 302)),
    ("/studio/experience/", (200, 302)),
    ("/siteconfig/customizer/", (200, 302)),
    ("/discover/", (200,)),
    ("/support/", (200,)),
    ("/verify/", (200,)),
]


@override_settings(ALLOWED_HOSTS=["*"])
class PhaseHCriticalPathsTests(TestCase):
    """
    Phase H: Critical URLs must not return 404 or 500.
    Uses TestCase (DB required): GET requests run through middleware and context processors
    (e.g. site_settings → get_effective_site_settings → RuntimeDefaults), which need DB.
    """

    def _assert_acceptable(self, path: str, allowed: tuple, urlconf: str):
        with self.settings(ROOT_URLCONF=urlconf):
            client = Client()
            response = client.get(path, follow=False)
        self.assertIn(
            response.status_code,
            allowed,
            f"{path} (ROOT_URLCONF={urlconf}) returned {response.status_code}; allowed {allowed}",
        )

    def test_manager_critical_paths_no_404_500(self):
        """With manager urlconf, critical paths must not return 404 or 500."""
        for path, allowed in MANAGER_CRITICAL_PATHS:
            with self.subTest(path=path):
                self._assert_acceptable(path, allowed, "config.manager_urls")

    def test_tenant_critical_paths_no_404_500(self):
        """With root urlconf, critical paths must not return 404 or 500."""
        for path, allowed in TENANT_CRITICAL_PATHS:
            with self.subTest(path=path):
                self._assert_acceptable(path, allowed, "config.urls")


class PhaseHErrorHandlersTests(TestCase):
    """Phase H: 403, 404, 500 handlers must render with correct status. Requires DB (template context)."""

    def test_404_handler_renders_on_manager(self):
        """404 handler returns 404 and renders content when public_host_kind is manager."""
        from config.urls import page_not_found

        request = HttpRequest()
        request.method = "GET"
        request.META["HTTP_HOST"] = "manager.runmycampus.com"
        request.public_host_kind = "manager"
        request.user = None
        response = page_not_found(request, Exception("Not found"))
        self.assertEqual(response.status_code, 404)
        self.assertGreater(len(response.content), 0, "404 response must have body")

    def test_404_handler_renders_on_tenant(self):
        """404 handler returns 404 and renders content when not manager."""
        from config.urls import page_not_found

        request = HttpRequest()
        request.method = "GET"
        request.META["HTTP_HOST"] = "testserver"
        request.public_host_kind = None
        request.user = None
        response = page_not_found(request, Exception("Not found"))
        self.assertEqual(response.status_code, 404)
        self.assertGreater(len(response.content), 0, "404 response must have body")

    def test_500_handler_renders_with_status_500(self):
        """500 handler returns status 500 and renders content."""
        from config.urls import server_error

        request = HttpRequest()
        request.method = "GET"
        request.META["HTTP_HOST"] = "testserver"
        request.public_host_kind = None
        request.user = None
        response = server_error(request)
        self.assertEqual(response.status_code, 500)
        self.assertGreater(len(response.content), 0, "500 response must have body")

    def test_500_handler_renders_on_manager(self):
        """500 handler returns 500 and renders on manager host."""
        from config.urls import server_error

        request = HttpRequest()
        request.method = "GET"
        request.META["HTTP_HOST"] = "manager.runmycampus.com"
        request.public_host_kind = "manager"
        request.user = None
        response = server_error(request)
        self.assertEqual(response.status_code, 500)
        self.assertGreater(len(response.content), 0, "500 response must have body")


class PhaseHUrlReverseTests(SimpleTestCase):
    """Phase H: Critical URL names must reverse without error (no 404 from misconfiguration)."""

    def test_super_dashboard_reverse(self):
        self.assertEqual(reverse("super:dashboard"), "/super/")

    def test_super_backlog_unlock_center_reverse(self):
        url = reverse("super:backlog_unlock_center")
        self.assertIn("/super/backlog-unlock-center/", url)

    def test_super_fleet_governed_changes_reverse(self):
        url = reverse("super:fleet_governed_changes")
        self.assertIn("/super/fleet-governed-changes/", url)

    def test_studio_experience_reverse(self):
        self.assertEqual(reverse("studio_os:experience"), "/studio/experience/")

    def test_studio_automation_reverse(self):
        self.assertEqual(reverse("studio_os:automation"), "/studio/automation/")

    def test_studio_output_reverse(self):
        self.assertEqual(reverse("studio_os:output"), "/studio/output/")

    def test_studio_launch_reverse(self):
        self.assertEqual(reverse("studio_os:launch"), "/studio/launch/")

    def test_studio_control_reverse(self):
        self.assertEqual(reverse("studio_os:control"), "/studio/control/")

    def test_siteconfig_dashboard_hub_resolves(self):
        """Siteconfig dashboard hub path resolves."""
        url = reverse("siteconfig:dashboard_hub")
        self.assertIn("/siteconfig/", url)

    def test_siteconfig_console_domains_hub_resolves(self):
        """Phase B bounded console (Configuration Control Center) must resolve on manager and tenant."""
        url = reverse("siteconfig:console_domains_hub")
        self.assertEqual(url, "/siteconfig/console/")

    def test_finance_dashboard_resolves(self):
        """Finance app dashboard (tenant) must resolve for Phase H link verification."""
        url = reverse("finance:dashboard")
        self.assertIn("/finance/", url)

    def test_analytics_dashboard_resolves(self):
        """Analytics app dashboard (tenant) must resolve for Phase H link verification."""
        url = reverse("analytics:dashboard")
        self.assertIn("/analytics/", url)

    def test_compliance_dashboard_resolves(self):
        """Compliance app dashboard (tenant) must resolve for Phase H link verification."""
        url = reverse("compliance:dashboard")
        self.assertIn("/compliance/", url)

    def test_evals_teacher_dashboard_resolves(self):
        """Evals app teacher dashboard (tenant) must resolve for Phase H link verification."""
        url = reverse("evals:teacher_dashboard")
        self.assertIn("/evals/", url)

    def test_backend_student_detail_reverse(self):
        """Student 360 (linkage-first) URL must reverse."""
        url = reverse("accounts:backend_student_detail", kwargs={"student_id": 1})
        self.assertIn("/backend/students/1/", url)

    def test_payroll_dashboard_resolves(self):
        """Payroll app dashboard (tenant) must resolve for Phase H link verification."""
        url = reverse("payroll:dashboard")
        self.assertIn("/payroll/", url)

    def test_automation_outcomes_console_resolves(self):
        """Automation app outcomes console (tenant) must resolve for Phase H link verification."""
        url = reverse("automation:outcomes_console")
        self.assertIn("/automation/", url)

    def test_communication_group_list_resolves(self):
        """Communication app group list (tenant) must resolve for Phase H link verification."""
        url = reverse("communication:group_list")
        self.assertIn("/communication/", url)

    def test_requests_dashboard_resolves(self):
        """Requests app dashboard (tenant) must resolve for Phase H link verification."""
        url = reverse("requests:dashboard")
        self.assertIn("/requests/", url)

    def test_academics_teacher_syllabus_hub_resolves(self):
        """Academics app teacher syllabus hub (tenant) must resolve for Phase H link verification."""
        url = reverse("academics:teacher_syllabus_hub")
        self.assertIn("/academics/", url)
