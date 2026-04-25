"""PATH III.33: backend first-login checklist links to Launch Studio + role/migration panes."""

from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.models import Permission, User
from apps.accounts.views import backend_dashboard
from apps.schools.models import School, SchoolMembership


@override_settings(ALLOWED_HOSTS=["*"])
class FirstLoginLaunchStudioLinkTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="LSchool",
            slug="ls",
            subdomain="ls",
            is_active=True,
        )
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.admin_user = User.objects.create_user(
            username="adm_ls",
            password="x",
            is_staff=True,
            role=User.Role.ADMIN,
        )
        self.admin_user.feature_permissions.add(manage_perm)
        SchoolMembership.objects.create(
            user=self.admin_user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.teacher = User.objects.create_user(
            username="t_ls",
            password="x",
            is_staff=True,
            role=User.Role.TEACHER,
        )
        self.teacher.feature_permissions.add(manage_perm)
        SchoolMembership.objects.create(
            user=self.teacher,
            school=self.school,
            role=User.Role.TEACHER,
            is_primary=True,
        )
        self.factory = RequestFactory()

    def _html(self, user):
        request = self.factory.get("/authentication/backend/")
        request.user = user
        request.school = self.school
        response = backend_dashboard(request)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_admin_sees_launch_overview_and_migration(self):
        html = self._html(self.admin_user)
        self.assertIn("studio/launch", html)
        self.assertIn("pane=overview", html)
        self.assertIn("pane=migration", html)

    def test_teacher_sees_preview_by_role_not_migration(self):
        html = self._html(self.teacher)
        self.assertIn("studio/launch", html)
        self.assertIn("pane=role_preview", html)
        self.assertIn("pane=overview", html)
        self.assertNotIn("pane=migration", html)
