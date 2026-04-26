"""Tag manager POST uses feature permission settings.manage (1006)."""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission as FeaturePermission, User
from apps.people.models import InformationTag
from apps.schools.models import School

_T_HOST = "tag-pol.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class TagManagerPostPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Tag Pol School",
            slug="tag-pol",
            subdomain="tag-pol",
            is_active=True,
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_T_HOST, raise_request_exception=False)

    def test_tag_create_post_forbidden_without_settings_manage(self):
        u = User.objects.create_user(
            username="tag_noperm",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        u.feature_permissions.clear()
        self.client.login(username="tag_noperm", password="x" * 8)
        path = reverse("siteconfig:tag_manager")
        resp = self.client.post(
            path,
            data={
                "name": "E2E Tag No Perm",
                "category": "GEN",
                "color_hex": "#3498db",
            },
        )
        self.assertEqual(resp.status_code, 403)

    def test_tag_create_post_allowed_with_feature_permission(self):
        u = User.objects.create_user(
            username="tag_yes",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        u.feature_permissions.add(self.perm_settings)
        self.client.login(username="tag_yes", password="x" * 8)
        path = reverse("siteconfig:tag_manager")
        resp = self.client.post(
            path,
            data={
                "name": "E2E Tag Allowed 1006",
                "category": "GEN",
                "color_hex": "#3498db",
            },
        )
        self.assertNotEqual(resp.status_code, 403)
        self.assertIn(resp.status_code, (302, 200))


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class TagManagerEditPostPolicyTests(TestCase):
    """1048: tag_manager_edit POST (save) uses same settings.manage gate as list/create."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Tag Edit School",
            slug="tag-pol",
            subdomain="tag-pol",
            is_active=True,
        )
        cls.tag = InformationTag.objects.create(
            school=cls.school,
            name="Policy Edit Tag",
            category=InformationTag.Category.GENERAL,
            color_hex="#3498db",
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_T_HOST, raise_request_exception=False)

    def test_tag_edit_save_post_forbidden_without_settings_manage(self):
        u = User.objects.create_user(
            username="tag_edit_noperm",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        u.feature_permissions.clear()
        self.client.login(username="tag_edit_noperm", password="x" * 8)
        path = reverse("siteconfig:tag_manager_edit", args=[self.tag.pk])
        resp = self.client.post(
            path,
            data={
                "action": "save",
                "name": "Renamed By No Perm",
                "category": "GEN",
                "color_hex": "#3498db",
            },
        )
        self.assertEqual(resp.status_code, 403)

    def test_tag_edit_save_post_not_forbidden_with_settings_manage(self):
        u = User.objects.create_user(
            username="tag_edit_yes",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        u.feature_permissions.add(self.perm_settings)
        self.client.login(username="tag_edit_yes", password="x" * 8)
        path = reverse("siteconfig:tag_manager_edit", args=[self.tag.pk])
        resp = self.client.post(
            path,
            data={
                "action": "save",
                "name": "Renamed Allowed 1048",
                "category": "GEN",
                "color_hex": "#3498db",
            },
        )
        self.assertNotEqual(resp.status_code, 403)
        self.assertEqual(resp.status_code, 302)
        self.tag.refresh_from_db()
        self.assertEqual(self.tag.name, "Renamed Allowed 1048")
