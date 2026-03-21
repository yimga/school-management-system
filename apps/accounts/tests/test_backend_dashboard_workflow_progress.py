"""Regression: backend dashboard must not NameError on _workflow_progress."""

from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import User
from apps.accounts.views import backend_dashboard
from apps.schools.models import School, SchoolMembership


@override_settings(ALLOWED_HOSTS=["*"])
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
