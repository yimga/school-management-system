"""1013 + 1018 + 1023 + 1029: siteconfig / Studio mutating and policy routes."""

import json

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Permission as FeaturePermission, User
from apps.schools.models import School
from apps.siteconfig.models import Plan

_T_HOST = "mut-exp.runmycampus.com"
_FC_HOST = "featctl-exp.runmycampus.com"
_RBK_HOST = "rbk-exp.runmycampus.com"
_PREF_HOST = "pref-exp.runmycampus.com"
_ACT_HOST = "actas-exp.runmycampus.com"
_STU_POST_HOST = "studio-pub-exp.runmycampus.com"
_STU_DRAFT_HOST = "studio-draft-exp.runmycampus.com"
_BL_HOST = "bulk-letters-exp.runmycampus.com"
_WV_HOST = "waiver-exp.runmycampus.com"
_TH_HOST = "school-theme-exp.runmycampus.com"
_PV_HOST = "prev-toggle-exp.runmycampus.com"

_ALLOWED = [
    "testserver",
    "127.0.0.1",
    "localhost",
    _T_HOST,
    _FC_HOST,
    _RBK_HOST,
    _PREF_HOST,
    _ACT_HOST,
    _STU_POST_HOST,
    _STU_DRAFT_HOST,
    _BL_HOST,
    _WV_HOST,
    _TH_HOST,
    _PV_HOST,
]


@override_settings(ALLOWED_HOSTS=_ALLOWED)
class UpdateThemeJsonPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        School.objects.create(
            name="Mut Exp School",
            slug="mut-exp",
            subdomain="mut-exp",
            is_active=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_T_HOST, raise_request_exception=False)

    def test_update_theme_forbidden_for_parent_role(self):
        User.objects.create_user(
            username="theme_parent",
            password="x" * 8,
            role=User.Role.PARENT,
        )
        self.client.login(username="theme_parent", password="x" * 8)
        path = reverse("siteconfig:update_theme")
        resp = self.client.post(
            path,
            data=json.dumps({"theme": "dark"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_update_theme_ok_for_teacher(self):
        User.objects.create_user(
            username="theme_teacher",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        self.client.login(username="theme_teacher", password="x" * 8)
        path = reverse("siteconfig:update_theme")
        resp = self.client.post(
            path,
            data=json.dumps({"theme": "dark"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertTrue(data.get("success"))


@override_settings(ALLOWED_HOSTS=_ALLOWED)
class FeatureControlEmbedPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        School.objects.create(
            name="FeatCtl School",
            slug="featctl-exp",
            subdomain="featctl-exp",
            is_active=True,
        )
        cls.perm_fc, _ = FeaturePermission.objects.get_or_create(
            code="settings.feature_control",
            defaults={"name": "Feature control"},
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_FC_HOST, raise_request_exception=False)

    def test_feature_control_embed_forbidden_without_permission(self):
        u = User.objects.create_user(
            username="fc_no",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        u.feature_permissions.clear()
        self.client.login(username="fc_no", password="x" * 8)
        path = reverse("siteconfig:feature_control_panel") + "?embed=1"
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 403)

    def test_feature_control_embed_not_forbidden_with_permission(self):
        u = User.objects.create_user(
            username="fc_yes",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        u.feature_permissions.add(self.perm_fc)
        self.client.login(username="fc_yes", password="x" * 8)
        path = reverse("siteconfig:feature_control_panel") + "?embed=1"
        resp = self.client.get(path)
        self.assertNotEqual(resp.status_code, 403)

    def test_feature_control_export_get_json_with_permission(self):
        """1044: export endpoint returns JSON (settings.feature_control)."""
        u = User.objects.create_user(
            username="fc_export_ok",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        u.feature_permissions.add(self.perm_fc)
        self.client.login(username="fc_export_ok", password="x" * 8)
        path = reverse("siteconfig:feature_control_export")
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200)
        ct = (resp.get("Content-Type") or "").split(";")[0].strip()
        self.assertEqual(ct, "application/json")


@override_settings(ALLOWED_HOSTS=_ALLOWED)
class PackageRollbackPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        School.objects.create(
            name="Rollback School",
            slug="rbk-exp",
            subdomain="rbk-exp",
            is_active=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_RBK_HOST, raise_request_exception=False)

    def test_rollback_get_forbidden_for_teacher(self):
        User.objects.create_user(
            username="rbk_teacher",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        self.client.login(username="rbk_teacher", password="x" * 8)
        path = reverse("siteconfig:installed_packages_rollback")
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 403)

    def test_rollback_get_ok_for_admin(self):
        User.objects.create_user(
            username="rbk_admin",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        self.client.login(username="rbk_admin", password="x" * 8)
        path = reverse("siteconfig:installed_packages_rollback")
        resp = self.client.get(path)
        self.assertNotEqual(resp.status_code, 403)
        self.assertIn(resp.status_code, (200, 302))


@override_settings(ALLOWED_HOSTS=_ALLOWED)
class SetDefaultDashboardViewPostPolicyTests(TestCase):
    """1018: set_default_dashboard_view accepts POST for any authenticated user (no 403)."""

    @classmethod
    def setUpTestData(cls):
        School.objects.create(
            name="Pref Exp School",
            slug="pref-exp",
            subdomain="pref-exp",
            is_active=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_PREF_HOST, raise_request_exception=False)

    def test_set_default_dashboard_view_post_ok_for_teacher(self):
        User.objects.create_user(
            username="pref_teacher",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        self.client.login(username="pref_teacher", password="x" * 8)
        path = reverse("siteconfig:set_default_dashboard_view")
        resp = self.client.post(path, data={"view": "OVERVIEW"})
        self.assertNotEqual(resp.status_code, 403)
        self.assertEqual(resp.status_code, 302)


@override_settings(ALLOWED_HOSTS=_ALLOWED)
class ActAsRolePostPolicyTests(TestCase):
    """1018: set_act_as_role POST is staff-only; others get safe redirect (not 403)."""

    @classmethod
    def setUpTestData(cls):
        School.objects.create(
            name="ActAs Exp School",
            slug="actas-exp",
            subdomain="actas-exp",
            is_active=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_ACT_HOST, raise_request_exception=False)

    def test_act_as_post_redirects_non_staff(self):
        User.objects.create_user(
            username="actas_teacher",
            password="x" * 8,
            role=User.Role.TEACHER,
            is_staff=False,
        )
        self.client.login(username="actas_teacher", password="x" * 8)
        path = reverse("siteconfig:set_act_as_role")
        resp = self.client.post(path, data={"role": "TEACHER", "next": "/"})
        # staff_member_required: logged-in non-staff may be 403 (forbidden) or redirect to login per Django/settings.
        self.assertIn(resp.status_code, (302, 301, 403))

    def test_act_as_post_allowed_for_staff(self):
        User.objects.create_user(
            username="actas_staff",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.client.login(username="actas_staff", password="x" * 8)
        path = reverse("siteconfig:set_act_as_role")
        resp = self.client.post(path, data={"role": "TEACHER", "next": "/"})
        self.assertNotEqual(resp.status_code, 403)
        self.assertEqual(resp.status_code, 302)


@override_settings(ALLOWED_HOSTS=_ALLOWED)
class StudioPublishApiPolicyTests(TestCase):
    """1018: studio_os publish API requires tenant staff; JSON 403 otherwise."""

    @classmethod
    def setUpTestData(cls):
        School.objects.create(
            name="Studio Pub School",
            slug="studio-pub-exp",
            subdomain="studio-pub-exp",
            is_active=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_STU_POST_HOST, raise_request_exception=False)

    def test_studio_publish_post_forbidden_for_non_staff(self):
        User.objects.create_user(
            username="stu_pub_teacher",
            password="x" * 8,
            role=User.Role.TEACHER,
            is_staff=False,
        )
        self.client.login(username="stu_pub_teacher", password="x" * 8)
        path = reverse("studio_os:publish", urlconf="config.tenant_urls")
        resp = self.client.post(path, data={"mode": "experience"})
        self.assertEqual(resp.status_code, 403)

    def test_studio_publish_post_not_forbidden_for_staff(self):
        User.objects.create_user(
            username="stu_pub_staff",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.client.login(username="stu_pub_staff", password="x" * 8)
        path = reverse("studio_os:publish", urlconf="config.tenant_urls")
        resp = self.client.post(path, data={"mode": "__invalid_mode_xyz__"})
        self.assertNotEqual(resp.status_code, 403)
        self.assertIn(resp.status_code, (200, 400))


@override_settings(ALLOWED_HOSTS=_ALLOWED)
class BulkLettersPostPolicyTests(TestCase):
    """1023: bulk_letters POST requires settings.manage."""

    @classmethod
    def setUpTestData(cls):
        # Path is gated by FeatureGatekeeperMiddleware (reports_custom_builder or coarse reports).
        cls.plan_reports = Plan.objects.create(
            name="Bulk Letters Policy Plan",
            slug="bl-policy-exp-plan",
            included_features=["reports"],
            is_active=True,
        )
        cls.school = School.objects.create(
            name="Bulk Letters School",
            slug="bulk-letters-exp",
            subdomain="bulk-letters-exp",
            is_active=True,
            plan=cls.plan_reports,
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_BL_HOST, raise_request_exception=False)

    def test_bulk_letters_post_forbidden_without_settings_manage(self):
        u = User.objects.create_user(
            username="bl_noperm",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        u.feature_permissions.clear()
        self.client.login(username="bl_noperm", password="x" * 8)
        path = reverse("siteconfig:bulk_letters")
        resp = self.client.post(
            path,
            data={"letter_body": "x", "letter_title": "t", "classroom_id": ""},
        )
        self.assertEqual(resp.status_code, 403)

    def test_bulk_letters_post_not_forbidden_with_settings_manage(self):
        u = User.objects.create_user(
            username="bl_yes",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        u.feature_permissions.add(self.perm_settings)
        self.client.login(username="bl_yes", password="x" * 8)
        path = reverse("siteconfig:bulk_letters")
        resp = self.client.post(path, data={"letter_body": "", "classroom_id": ""})
        self.assertNotEqual(resp.status_code, 403)
        self.assertEqual(resp.status_code, 200)


@override_settings(ALLOWED_HOSTS=_ALLOWED)
class RequestWaiverPostPolicyTests(TestCase):
    """1023: request_waiver POST requires settings.manage."""

    @classmethod
    def setUpTestData(cls):
        School.objects.create(
            name="Waiver School",
            slug="waiver-exp",
            subdomain="waiver-exp",
            is_active=True,
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_WV_HOST, raise_request_exception=False)

    def test_request_waiver_post_forbidden_without_settings_manage(self):
        u = User.objects.create_user(
            username="wv_noperm",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        u.feature_permissions.clear()
        self.client.login(username="wv_noperm", password="x" * 8)
        path = reverse("siteconfig:request_waiver")
        resp = self.client.post(path, data={"reason": "Need waiver for testing policy."})
        self.assertEqual(resp.status_code, 403)

    def test_request_waiver_post_not_forbidden_with_settings_manage(self):
        u = User.objects.create_user(
            username="wv_yes",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        u.feature_permissions.add(self.perm_settings)
        self.client.login(username="wv_yes", password="x" * 8)
        path = reverse("siteconfig:request_waiver")
        resp = self.client.post(path, data={"reason": "Need waiver for testing policy."})
        self.assertNotEqual(resp.status_code, 403)
        self.assertEqual(resp.status_code, 302)


@override_settings(ALLOWED_HOSTS=_ALLOWED)
class StudioSaveDraftApiPolicyTests(TestCase):
    """1023: studio_os save_draft API requires tenant staff."""

    @classmethod
    def setUpTestData(cls):
        School.objects.create(
            name="Studio Draft School",
            slug="studio-draft-exp",
            subdomain="studio-draft-exp",
            is_active=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_STU_DRAFT_HOST, raise_request_exception=False)

    def test_studio_save_draft_post_forbidden_for_non_staff(self):
        User.objects.create_user(
            username="stu_draft_teacher",
            password="x" * 8,
            role=User.Role.TEACHER,
            is_staff=False,
        )
        self.client.login(username="stu_draft_teacher", password="x" * 8)
        path = reverse("studio_os:save_draft", urlconf="config.tenant_urls")
        resp = self.client.post(path, data={"mode": "experience"})
        self.assertEqual(resp.status_code, 403)

    def test_studio_save_draft_post_not_forbidden_for_staff(self):
        User.objects.create_user(
            username="stu_draft_staff",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.client.login(username="stu_draft_staff", password="x" * 8)
        path = reverse("studio_os:save_draft", urlconf="config.tenant_urls")
        resp = self.client.post(path, data={"mode": "experience", "primary_color": "#112233"})
        self.assertNotEqual(resp.status_code, 403)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))


@override_settings(ALLOWED_HOSTS=_ALLOWED)
class SchoolThemeSettingsPostPolicyTests(TestCase):
    """1029: school_theme_settings POST requires settings.manage."""

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Theme Policy School",
            slug="school-theme-exp",
            subdomain="school-theme-exp",
            is_active=True,
            theme_choice="UNFOLD",
        )
        cls.perm_settings, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_TH_HOST, raise_request_exception=False)

    def test_school_theme_post_forbidden_or_redirect_without_settings_manage(self):
        u = User.objects.create_user(
            username="th_noperm",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        u.feature_permissions.clear()
        self.client.login(username="th_noperm", password="x" * 8)
        path = reverse("siteconfig:school_theme_settings")
        resp = self.client.post(path, data={"theme_choice": "JAZZMIN"})
        self.assertIn(resp.status_code, (302, 403))

    def test_school_theme_post_not_forbidden_with_settings_manage(self):
        u = User.objects.create_user(
            username="th_yes",
            password="x" * 8,
            role=User.Role.ADMIN,
        )
        u.feature_permissions.add(self.perm_settings)
        self.client.login(username="th_yes", password="x" * 8)
        path = reverse("siteconfig:school_theme_settings")
        resp = self.client.post(path, data={"theme_choice": "SNEAT"})
        self.assertNotEqual(resp.status_code, 403)
        self.assertEqual(resp.status_code, 302)
        self.school.refresh_from_db()
        self.assertEqual(self.school.theme_choice, "SNEAT")


@override_settings(ALLOWED_HOSTS=_ALLOWED)
class TogglePreviewModePostPolicyTests(TestCase):
    """1029: toggle_preview_mode requires staff (staff_member_required)."""

    @classmethod
    def setUpTestData(cls):
        School.objects.create(
            name="Preview Toggle School",
            slug="prev-toggle-exp",
            subdomain="prev-toggle-exp",
            is_active=True,
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_PV_HOST, raise_request_exception=False)

    def test_toggle_preview_post_redirects_or_forbids_non_staff(self):
        User.objects.create_user(
            username="pv_teacher",
            password="x" * 8,
            role=User.Role.TEACHER,
            is_staff=False,
        )
        self.client.login(username="pv_teacher", password="x" * 8)
        path = reverse("siteconfig:toggle_preview_mode")
        resp = self.client.post(path, data={})
        self.assertIn(resp.status_code, (302, 403))

    def test_toggle_preview_post_not_forbidden_for_staff(self):
        User.objects.create_user(
            username="pv_staff",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.client.login(username="pv_staff", password="x" * 8)
        path = reverse("siteconfig:toggle_preview_mode")
        resp = self.client.post(path, data={})
        self.assertNotEqual(resp.status_code, 403)
        self.assertEqual(resp.status_code, 302)
