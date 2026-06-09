"""Platform API v1 tenant CRUD — marketplace scope enforcement."""

from __future__ import annotations

from unittest.mock import Mock

from django.test import SimpleTestCase
from django.urls import reverse

from apps.api.permissions import MarketplaceAppScopedPermission, V1_TENANT_CRUD_SCOPE_MAP


class MarketplaceAppScopedPermissionTests(SimpleTestCase):
    def _allows(self, *, scopes, basename: str, action: str, app_bound: bool = True) -> bool:
        request = Mock()
        request.app_installation = object() if app_bound else None
        request.app_scope = frozenset(scopes)
        view = Mock(basename=basename, action=action)
        return MarketplaceAppScopedPermission().has_permission(request, view)

    def test_session_auth_passes_without_app_installation(self) -> None:
        self.assertTrue(
            self._allows(scopes=(), basename="students", action="list", app_bound=False)
        )

    def test_students_list_requires_students_read(self) -> None:
        self.assertFalse(self._allows(scopes={"finance:read"}, basename="students", action="list"))
        self.assertTrue(self._allows(scopes={"students:read"}, basename="students", action="list"))

    def test_students_create_requires_students_write(self) -> None:
        self.assertFalse(self._allows(scopes={"students:read"}, basename="students", action="create"))
        self.assertTrue(self._allows(scopes={"students:write"}, basename="students", action="create"))

    def test_evaluations_create_requires_grades_write(self) -> None:
        self.assertFalse(self._allows(scopes={"grades:read"}, basename="evaluations", action="create"))
        self.assertTrue(self._allows(scopes={"grades:write"}, basename="evaluations", action="create"))

    def test_invoices_list_requires_finance_read(self) -> None:
        self.assertFalse(self._allows(scopes={"students:read"}, basename="invoices", action="list"))
        self.assertTrue(self._allows(scopes={"finance:read"}, basename="invoices", action="list"))

    def test_unknown_action_denied_when_app_bound(self) -> None:
        self.assertFalse(
            self._allows(scopes={"students:read"}, basename="students", action="unknown_action")
        )

    def test_scope_map_covers_all_v1_crud_basenames(self) -> None:
        basenames = {"students", "teachers", "guardians", "evaluations", "invoices", "payments"}
        mapped = {b for b, _ in V1_TENANT_CRUD_SCOPE_MAP}
        self.assertTrue(basenames.issubset(mapped))


class V1TenantCrudRouteTests(SimpleTestCase):
    def test_named_list_routes_reverse(self) -> None:
        for name in (
            "students-list",
            "teachers-list",
            "guardians-list",
            "evaluations-list",
            "invoices-list",
            "payments-list",
        ):
            path = reverse(f"api_v1:{name}")
            self.assertTrue(path.startswith("/api/v1/"), msg=f"{name} -> {path}")
