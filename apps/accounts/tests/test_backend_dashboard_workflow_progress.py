"""Regression: backend dashboard must not NameError on _workflow_progress."""

from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import User
from apps.accounts.views import backend_dashboard
from apps.schools.models import School, SchoolMembership


# backend_dashboard is served on the tenant host, whose urlconf (config.tenant_urls)
# registers the admin site so admin_site.each_context()'s reverse("admin:app_list")
# resolves. Calling the view directly via RequestFactory bypasses the host middleware
# that would set that urlconf, so pin ROOT_URLCONF to the real serving urlconf.
@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class BackendDashboardWorkflowProgressTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="T",
            slug="t-wf",
            subdomain="t-wf",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="adm_wf",
            password="x",
            is_staff=True,
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        self.factory = RequestFactory()

    def test_backend_dashboard_renders_without_nameerror(self):
        request = self.factory.get("/authentication/backend/")
        request.user = self.user
        request.school = self.school
        try:
            response = backend_dashboard(request)
        except NameError as e:
            self.fail(f"backend_dashboard raised NameError: {e}")
        self.assertIn(response.status_code, (200, 302))
