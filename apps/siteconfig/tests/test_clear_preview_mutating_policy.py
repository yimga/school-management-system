"""Preview clear route uses settings.manage (1006B)."""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission as FeaturePermission, User
from apps.schools.models import School, SchoolMembership

_T_HOST = "clr-preview.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class ClearPreviewGetPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Clear Preview School",
            slug="clr-preview",
            subdomain="clr-preview",
            is_active=True,
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_T_HOST, raise_request_exception=False)

    def test_clear_preview_forbidden_without_settings_manage(self):
        u = User.objects.create_user(
            username="clr_prev_no",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        u.feature_permissions.clear()
        SchoolMembership.objects.create(
            user=u, school=self.school, role=User.Role.TEACHER, is_primary=True
        )
        self.client.login(username="clr_prev_no", password="x" * 8)
        path = reverse("siteconfig:clear_preview")
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 403)

    def test_clear_preview_redirects_with_feature_permission(self):
        u = User.objects.create_user(
            username="clr_prev_yes",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        u.feature_permissions.add(self.perm_settings)
        self.client.login(username="clr_prev_yes", password="x" * 8)
        path = reverse("siteconfig:clear_preview")
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 302)
        self.assertNotEqual(resp.status_code, 403)
