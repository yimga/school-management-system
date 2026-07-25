"""Impersonation consent grant/revoke POST uses settings.manage (1006B)."""

import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission as FeaturePermission, User
from apps.schools.models import School, SchoolMembership

_T_HOST = "imp-consent.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class ImpersonationConsentPostPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Impersonation Consent School",
            slug="imp-consent",
            subdomain="imp-consent",
            is_active=True,
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_T_HOST, raise_request_exception=False)

    def test_grant_post_forbidden_without_settings_manage(self):
        u = User.objects.create_user(
            username="imp_no",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        u.feature_permissions.clear()
        SchoolMembership.objects.create(
            user=u, school=self.school, role=User.Role.TEACHER, is_primary=True
        )
        self.client.login(username="imp_no", password="x" * 8)
        path = reverse("siteconfig:grant_impersonation_consent")
        resp = self.client.post(path)
        self.assertEqual(resp.status_code, 403)

    def test_grant_post_ok_json_with_feature_permission(self):
        u = User.objects.create_user(
            username="imp_yes",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        u.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.create(
            user=u, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        self.client.login(username="imp_yes", password="x" * 8)
        path = reverse("siteconfig:grant_impersonation_consent")
        resp = self.client.post(path)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertTrue(data.get("ok"))

    def test_revoke_post_forbidden_without_settings_manage(self):
        u = User.objects.create_user(
            username="imp_rev_no",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        u.feature_permissions.clear()
        SchoolMembership.objects.create(
            user=u, school=self.school, role=User.Role.TEACHER, is_primary=True
        )
        self.client.login(username="imp_rev_no", password="x" * 8)
        path = reverse("siteconfig:revoke_impersonation_consent")
        resp = self.client.post(path)
        self.assertEqual(resp.status_code, 403)

    def test_revoke_post_ok_json_with_feature_permission(self):
        u = User.objects.create_user(
            username="imp_rev_yes",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        u.feature_permissions.add(self.perm_settings)
        SchoolMembership.objects.create(
            user=u, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        self.client.login(username="imp_rev_yes", password="x" * 8)
        path = reverse("siteconfig:revoke_impersonation_consent")
        resp = self.client.post(path)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertTrue(data.get("ok"))
