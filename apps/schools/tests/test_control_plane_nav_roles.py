"""Phase 1 — sidebar role awareness (no DB)."""

from django.test import RequestFactory, SimpleTestCase

from apps.schools.control_plane_nav import build_control_plane_nav


class _UserStub:
    is_authenticated = True
    is_staff = True

    def __init__(self, *, is_superuser: bool):
        self.is_superuser = is_superuser


class ControlPlaneNavRoleTests(SimpleTestCase):
    def _all_item_ids(self, nav):
        ids = []
        for g in nav:
            for it in g.get("items") or []:
                iid = it.get("id")
                if iid:
                    ids.append(iid)
        return ids

    def test_advanced_nav_omits_platform_admin_bridges_for_all_roles(self):
        for is_superuser in (False, True):
            with self.subTest(is_superuser=is_superuser):
                request = RequestFactory().get("/super/dashboard/")
                request.urlconf = "config.manager_urls"
                request.user = _UserStub(is_superuser=is_superuser)
                nav = build_control_plane_nav(request)
                ids = self._all_item_ids(nav)
                self.assertFalse(
                    any(iid.startswith("cp_admin_bridge_") for iid in ids),
                    msg="Platform admin bridge sidebar links retired",
                )
                self.assertNotIn(
                    "cp_platform_backoffice",
                    ids,
                    msg="Platform backoffice sidebar link retired",
                )
