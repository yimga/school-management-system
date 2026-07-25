"""POST sync conflict resolution uses feature permission settings.manage (1006)."""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission as FeaturePermission, User
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import SyncConflict


_T_HOST = "sync-pol.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class SyncCenterResolvePermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Sync Pol School",
            slug="sync-pol",
            subdomain="sync-pol",
            is_active=True,
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_T_HOST, raise_request_exception=False)
        SyncConflict.objects.filter(school=self.school).delete()
        c = SyncConflict.objects.create(
            school=self.school,
            entity_type="policy_test",
            entity_id=42,
            status=SyncConflict.Status.PENDING,
        )
        self._conflict_id = c.pk

    def test_resolve_post_forbidden_without_settings_manage(self):
        u = User.objects.create_user(
            username="sync_noperm",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        u.feature_permissions.clear()
        SchoolMembership.objects.create(
            user=u, school=self.school, role=User.Role.TEACHER, is_primary=True
        )
        self.client.login(username="sync_noperm", password="x" * 8)
        path = reverse("siteconfig:sync_center_resolve", args=[self._conflict_id])
        resp = self.client.post(path, data={"resolution": "discard"})
        self.assertEqual(resp.status_code, 403)

    def test_resolve_post_not_forbidden_with_feature_permission(self):
        u = User.objects.create_user(
            username="sync_yes",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        u.feature_permissions.add(self.perm_settings)
        self.client.login(username="sync_yes", password="x" * 8)
        path = reverse("siteconfig:sync_center_resolve", args=[self._conflict_id])
        resp = self.client.post(path, data={"resolution": "discard"})
        self.assertNotEqual(resp.status_code, 403)
        self.assertEqual(resp.status_code, 302)
