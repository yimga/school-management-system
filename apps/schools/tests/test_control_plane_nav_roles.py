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

    def test_platform_backoffice_link_hidden_for_non_superuser(self):
        request = RequestFactory().get("/super/dashboard/")
        request.urlconf = "config.manager_urls"
        request.user = _UserStub(is_superuser=False)
        nav = build_control_plane_nav(request)
        self.assertNotIn(
            "cp_platform_backoffice",
            self._all_item_ids(nav),
            msg="Advanced Django admin sidebar link is superuser-only",
        )

    def test_platform_backoffice_link_shown_for_superuser(self):
        request = RequestFactory().get("/super/dashboard/")
        request.urlconf = "config.manager_urls"
        request.user = _UserStub(is_superuser=True)
        nav = build_control_plane_nav(request)
        self.assertIn("cp_platform_backoffice", self._all_item_ids(nav))
