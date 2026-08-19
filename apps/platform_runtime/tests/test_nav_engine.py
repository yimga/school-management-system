"""Nav engine catalog + tenant/operator projectors."""

from __future__ import annotations

from pathlib import Path
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from apps.platform_runtime.nav_engine import (
    OPERATOR_SPINE_IDS,
    STAFF_PRIMARY_ROLES,
    TENANT_STAFF_SPINE_IDS,
    catalog_ids,
    command_bar_extra_defs,
    is_staff_primary_role,
    operator_items_for_group,
    spine_specs,
)
from apps.siteconfig.portal_sidebar_items import build_portal_sidebar_items

User = get_user_model()


def _site():
    return SimpleNamespace(
        enable_student_portal=True,
        enable_parent_portal=True,
        get_feature_control_settings=lambda: {"portal_features": {}},
    )


class NavEngineCatalogTests(SimpleTestCase):
    def test_required_tenant_spine_ids(self):
        ids = catalog_ids()
        for item_id in TENANT_STAFF_SPINE_IDS:
            self.assertIn(item_id, ids)

    def test_operator_groups_match_control_plane_labels(self):
        from apps.platform_runtime.nav_engine import OPERATOR_SPINE

        cp = (
            Path(__file__).resolve().parents[3]
            / "apps"
            / "schools"
            / "control_plane_nav.py"
        ).read_text(encoding="utf-8")
        for spec in OPERATOR_SPINE:
            self.assertIn(f'"{spec.group}"', cp, msg=spec.group)

    def test_hod_is_staff_primary(self):
        self.assertIn("HOD", STAFF_PRIMARY_ROLES)
        self.assertTrue(is_staff_primary_role("HOD"))
        self.assertFalse(is_staff_primary_role("TEACHER"))
        self.assertFalse(is_staff_primary_role("PARENT"))

    def test_operator_hubs_attach_to_existing_groups(self):
        overview = operator_items_for_group("Platform Overview")
        self.assertTrue(any(row["id"] == "super_founder_dashboard" for row in overview))
        tenants = operator_items_for_group("Tenants")
        self.assertTrue(any(row["id"] == "super_fleet_wall" for row in tenants))

    def test_command_bar_extras_cover_teachers(self):
        names = {row[3] for row in command_bar_extra_defs()}
        self.assertIn("accounts:backend_teacher_list", names)
        self.assertIn("super:founder_dashboard", names)

    def test_spine_plane_filter(self):
        tenant = {spec.id for spec in spine_specs(plane="tenant")}
        self.assertIn("teachers", tenant)
        self.assertNotIn("super_founder_dashboard", tenant)


@override_settings(ROOT_URLCONF="config.tenant_urls")
class NavEngineTenantProjectorTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = _site()
    def setUp(self):
        self.factory = RequestFactory()
        self.site = _site()

    def _items(self, user, *, session_role=None):
        request = self.factory.get("/backend/")
        request.user = user
        request.session = {}
        request.messages_unread_count = 0
        if session_role:
            request.session["active_portal_role"] = session_role
        with patch(
            "apps.siteconfig.portal_sidebar_items._backend_flags_for_sidebar",
            return_value={},
        ), patch(
            "apps.siteconfig.portal_sidebar_items._cached_sidebar_badge_counts",
            return_value=(None, None, None),
        ), patch(
            "apps.accounts.portal_roles.get_nav_portal_role",
            return_value=user.role,
        ):
            return build_portal_sidebar_items(request, self.site)

    def _user(self, *, role, is_staff=False):
        user = SimpleNamespace(
            is_authenticated=True,
            role=role,
            is_staff=is_staff,
            is_superuser=False,
            pk=None,
            has_feature_permission=lambda _code: False,
        )
        return user

    def test_admin_sees_teacher_classroom_year_sync(self):
        user = self._user(role=User.Role.ADMIN, is_staff=True)
        ids = {it.get("id") for it in self._items(user)}
        for item_id in ("teachers", "classrooms", "academic_years", "sync_center"):
            self.assertIn(item_id, ids, msg=item_id)

    def test_hod_sees_staff_people_nav(self):
        user = self._user(role=User.Role.HOD)
        ids = {it.get("id") for it in self._items(user)}
        self.assertIn("teachers", ids)
        self.assertIn("classrooms", ids)
        self.assertNotIn("feature_control", ids)

    def test_parent_does_not_see_staff_spine(self):
        user = self._user(role=User.Role.PARENT)
        ids = {it.get("id") for it in self._items(user)}
        for item_id in TENANT_STAFF_SPINE_IDS:
            self.assertNotIn(item_id, ids, msg=item_id)

    def test_teacher_hat_does_not_see_staff_spine(self):
        user = self._user(role=User.Role.TEACHER)
        ids = {it.get("id") for it in self._items(user)}
        self.assertNotIn("teachers", ids)
        self.assertNotIn("feature_control", ids)
        self.assertIn("teacher_workflow", ids)


class NavEngineOperatorProjectorTests(SimpleTestCase):
    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_super_spine_includes_founder_and_fleet_wall(self):
        from apps.schools.manager_nav_convergence import (
            build_manager_complete_sidebar_groups,
        )

        request = RequestFactory().get("/super/")
        request.urlconf = "config.manager_urls"
        request.user = User(is_superuser=True, is_staff=True, username="nav_op")
        request.public_host_kind = "manager"
        ids = []
        for group in build_manager_complete_sidebar_groups(request):
            for item in group.get("items") or []:
                ids.append(item.get("id"))
        self.assertIn("super_founder_dashboard", ids)
        self.assertIn("super_fleet_wall", ids)
        self.assertIn("super_marketplace_installation_health", ids)
        for required in OPERATOR_SPINE_IDS:
            if required == "super_orchestration_workbench":
                continue  # config surface — not on /super/ ops spine
            self.assertIn(required, ids, msg=required)

    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_admin_config_spine_includes_orchestration(self):
        from apps.schools.manager_nav_convergence import (
            build_manager_complete_sidebar_groups,
        )

        request = RequestFactory().get("/admin/")
        request.urlconf = "config.manager_urls"
        request.user = User(is_superuser=True, is_staff=True, username="nav_op_admin")
        request.public_host_kind = "manager"
        ids = [
            item.get("id")
            for group in build_manager_complete_sidebar_groups(request)
            for item in group.get("items") or []
        ]
        self.assertIn("super_orchestration_workbench", ids)
        self.assertNotIn("super_founder_dashboard", ids)


class NavEngineUrlIntegrityTests(SimpleTestCase):
    def test_tenant_spine_url_names_reverse(self):
        from django.urls import NoReverseMatch, set_urlconf

        set_urlconf("config.tenant_urls")
        from apps.platform_runtime.nav_engine import TENANT_STAFF_SPINE

        for spec in TENANT_STAFF_SPINE:
            try:
                url = reverse(spec.url_name)
            except NoReverseMatch as exc:
                self.fail(f"{spec.id} {spec.url_name}: {exc}")
            self.assertTrue(url)

    def test_operator_spine_url_names_reverse(self):
        from django.urls import NoReverseMatch, set_urlconf

        set_urlconf("config.manager_urls")
        from apps.platform_runtime.nav_engine import OPERATOR_SPINE

        for spec in OPERATOR_SPINE:
            try:
                url = reverse(spec.url_name, urlconf="config.manager_urls")
            except NoReverseMatch as exc:
                self.fail(f"{spec.id} {spec.url_name}: {exc}")
            self.assertTrue(url)
