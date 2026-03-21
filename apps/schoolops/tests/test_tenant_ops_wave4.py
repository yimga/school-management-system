"""Wave 4 tenant ops hub and module-gated CRUD surfaces."""

import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.schoolops.models import CanteenMeal, InventoryItem, LibraryItem, Route
from apps.schoolops.views_tenant_ops import (
    ops_canteen,
    ops_hub,
    ops_library,
    ops_transport,
)
from apps.schools.models import School

User = get_user_model()


class TenantOpsWave4Tests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Ops School",
            slug=f"ops-{uuid.uuid4().hex[:10]}",
            subdomain=f"ops-{uuid.uuid4().hex[:10]}",
            features={
                "library": True,
                "transport": True,
                "inventory": True,
                "canteen": True,
            },
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email="a@t.test",
            password="x",
            role=User.Role.ADMIN,
        )

    def _req(self, method, path, data=None):
        if method == "GET":
            r = self.factory.get(path)
        else:
            r = self.factory.post(path, data or {})
        r.user = self.admin
        r.school = self.school
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def test_hub_lists_modules(self):
        r = ops_hub(self._req("GET", "/backend/ops/"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Library")

    def test_library_add(self):
        r = ops_library(
            self._req(
                "POST",
                "/lib/",
                {"title": "Intro Algebra", "author": "Smith", "copies_total": "3"},
            )
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(
            LibraryItem.objects.filter(school=self.school, title="Intro Algebra").exists()
        )

    def test_transport_add_route(self):
        r = ops_transport(
            self._req(
                "POST",
                "/tr/",
                {"name": "North loop", "first_stop": "Gate A"},
            )
        )
        self.assertEqual(r.status_code, 302)
        route = Route.objects.get(school=self.school, name="North loop")
        self.assertEqual(route.stops.count(), 1)

    def test_inventory_add(self):
        from apps.schoolops.views_tenant_ops import ops_inventory

        r = ops_inventory(
            self._req(
                "POST",
                "/inv/",
                {"name": "Chalk", "quantity": "50", "location": "Store"},
            )
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(InventoryItem.objects.filter(school=self.school, name="Chalk").exists())

    def test_canteen_add(self):
        r = ops_canteen(
            self._req("POST", "/can/", {"name": "Lunch plate", "price": "2.50"})
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(
            CanteenMeal.objects.filter(school=self.school, name="Lunch plate").exists()
        )

    @patch("apps.schools.models.is_feature_enabled")
    def test_library_forbidden_without_feature(self, mock_feat):
        mock_feat.return_value = False
        bare = School.objects.create(
            name="Bare",
            slug=f"b-{uuid.uuid4().hex[:10]}",
            subdomain=f"b-{uuid.uuid4().hex[:10]}",
            features={},
        )
        r = self.factory.get("/lib/")
        r.user = self.admin
        r.school = bare
        resp = ops_library(r)
        self.assertEqual(resp.status_code, 403)
