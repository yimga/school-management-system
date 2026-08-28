from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from apps.siteconfig.admin_navigation_contracts import (
    AdminDestination,
    AdminPageContract,
    build_admin_page_contract,
    build_admin_recommendations,
)
from apps.siteconfig.admin_navigation_preferences import (
    AdminNavigationPreferenceService,
    NavigationRevisionConflict,
    _resolve_entries,
)
from apps.siteconfig.models_dashboard import AdminNavigationPreference


class AdminNavigationV3ServerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="admin-nav-v3", email="admin-nav-v3@example.test", password="test-only"
        )

    def setUp(self):
        self.home = AdminDestination(
            id="tenant_admin:home",
            label="Admin home",
            path="/admin/",
            group="Start",
            kind="home",
            scope="tenant",
        )
        self.years = AdminDestination(
            id="tenant_admin:academics:academicyear:list",
            label="Academic years",
            path="/admin/academics/academicyear/",
            group="Academic management",
            kind="model",
            scope="tenant",
        )
        self.registry = (self.home, self.years)

    def mutate(self, *, revision, mutation_id, mutation_type, payload=None, host="school.runmycampus.com"):
        return AdminNavigationPreferenceService.mutate(
            user=self.user,
            host=host,
            admin_site="tenant_admin",
            expected_revision=revision,
            mutation={"id": mutation_id, "type": mutation_type, "payload": payload or {}},
            destinations=self.registry,
            recommendation_ids={"recommendation:test"},
        )

    def test_semantic_mutations_are_revisioned_ordered_and_idempotent(self):
        first = self.mutate(
            revision=0,
            mutation_id="nav:test-pin-0001",
            mutation_type="pin",
            payload={"destinationId": self.years.id},
        )
        self.assertEqual(first["revision"], 1)
        self.assertEqual(first["state"]["pinned"][0]["id"], self.years.id)
        duplicate = self.mutate(
            revision=0,
            mutation_id="nav:test-pin-0001",
            mutation_type="pin",
            payload={"destinationId": self.years.id},
        )
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["revision"], 1)
        second = self.mutate(
            revision=1,
            mutation_id="nav:test-home-0002",
            mutation_type="pin",
            payload={"destinationId": self.home.id},
        )
        moved = self.mutate(
            revision=2,
            mutation_id="nav:test-move-0003",
            mutation_type="move_pin",
            payload={"destinationId": self.home.id, "index": 0},
        )
        self.assertEqual([item["id"] for item in moved["state"]["pinned"]], [self.home.id, self.years.id])
        self.assertEqual(second["revision"], 2)

    def test_stale_revision_returns_safe_conflict_without_overwrite(self):
        self.mutate(
            revision=0,
            mutation_id="nav:test-focus-0001",
            mutation_type="set_focus",
            payload={"enabled": True},
        )
        with self.assertRaises(NavigationRevisionConflict) as captured:
            self.mutate(
                revision=0,
                mutation_id="nav:test-mode-0002",
                mutation_type="set_mode",
                payload={"mode": "compact"},
            )
        self.assertEqual(captured.exception.actual_revision, 1)
        self.assertTrue(captured.exception.state["focus"])

    def test_host_port_and_admin_site_are_isolated(self):
        self.mutate(
            revision=0,
            mutation_id="nav:test-port-0001",
            mutation_type="set_mode",
            payload={"mode": "compact"},
            host="school.runmycampus.com:8443",
        )
        self.assertEqual(
            AdminNavigationPreferenceService.read_envelope(
                user=self.user, host="school.runmycampus.com", admin_site="tenant_admin"
            )["state"]["mode"],
            "compact",
        )
        self.assertEqual(
            AdminNavigationPreferenceService.read_envelope(
                user=self.user, host="school.runmycampus.com", admin_site="admin"
            )["state"]["mode"],
            "expanded",
        )
        self.assertEqual(AdminNavigationPreference.objects.count(), 1)

    def test_invalid_destination_and_payload_fail_closed(self):
        with self.assertRaises(ValidationError):
            self.mutate(
                revision=0,
                mutation_id="nav:test-invalid-0001",
                mutation_type="pin",
                payload={"destinationId": "operator:fleet"},
            )
        with self.assertRaises(ValidationError):
            self.mutate(
                revision=0,
                mutation_id="nav:test-invalid-0002",
                mutation_type="set_focus",
                payload={"enabled": "yes"},
            )

    def test_revoked_destination_is_not_rendered_but_diagnostic_state_survives(self):
        state = {
            "pinned": [
                {"id": self.years.id, "path": self.years.path, "label": self.years.label},
                {"id": "operator:fleet", "path": "/admin/fleet/", "label": "Fleet"},
            ]
        }
        rendered = _resolve_entries(state, {self.years.id: self.years})
        self.assertEqual([item["id"] for item in rendered["pinned"]], [self.years.id])
        self.assertEqual(len(state["pinned"]), 2)

    def test_page_archetypes_produce_genuine_page_specific_actions(self):
        request = RequestFactory().get("/admin/academics/academicyear/7/history/")
        request.resolver_match = SimpleNamespace(
            url_name="academics_academicyear_history",
            kwargs={"object_id": "7", "app_label": "academics", "model_name": "academicyear"},
        )
        site = SimpleNamespace(name="tenant_admin", index_title="Configuration")
        page = build_admin_page_contract(request, site, self.registry)
        self.assertEqual(page.archetype, "history")
        self.assertEqual(page.object_id, "7")
        self.assertTrue(any(action.label == "Back to record" for action in page.actions))

    def test_generic_index_recommendations_are_operator_only(self):
        page = AdminPageContract("index", self.home.id, "Admin home", "/admin/")
        self.assertEqual(build_admin_recommendations(page=page, destinations=self.registry, is_platform=False), ())
        operator = build_admin_recommendations(page=page, destinations=self.registry, is_platform=True)
        self.assertLessEqual(len(operator), 3)
        self.assertTrue(all(item.reason_code == "page_workflow:index" for item in operator))
