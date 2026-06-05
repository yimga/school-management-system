"""v4.00.91 Wave B — quick actions registry tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.assist_dock.quick_actions import (
    QuickAction,
    action_as_jsonable,
    actions_as_jsonable,
    actions_for,
    normalize_workspace_path,
    register_quick_action,
    reset_actions_for_tests,
)


class QuickActionValidationTests(SimpleTestCase):
    def test_normalize_workspace_path_strips_tenant_prefix(self):
        self.assertEqual(
            normalize_workspace_path("/t/demo-school/portal/parent/"),
            "/portal/parent/",
        )
        self.assertEqual(normalize_workspace_path("/portal/parent/"), "/portal/parent/")

    def test_id_required(self):
        with self.assertRaises(ValueError):
            QuickAction(id="", label="x", icon="bi-x", href="/x/")

    def test_href_or_url_name_required(self):
        with self.assertRaises(ValueError):
            QuickAction(id="x", label="x", icon="bi-x")

    def test_valid_action_constructs(self):
        a = QuickAction(id="x", label="X", icon="bi-x", href="/x/")
        self.assertEqual(a.id, "x")
        self.assertEqual(a.href, "/x/")


class FilterTests(SimpleTestCase):
    def setUp(self):
        reset_actions_for_tests()

    def tearDown(self):
        reset_actions_for_tests()

    def test_no_actions_returns_empty(self):
        self.assertEqual(actions_for(surface="portal", role="TEACHER"), [])

    def test_path_prefix_match(self):
        register_quick_action(
            QuickAction(
                id="reconcile",
                label="Reconcile",
                icon="bi-cash",
                href="/finance/reconcile/",
                path_prefixes=("/finance/",),
            )
        )
        register_quick_action(
            QuickAction(
                id="export",
                label="Export",
                icon="bi-download",
                href="/export/",
                path_prefixes=("/reports/",),
            )
        )
        visible = {a.id for a in actions_for(surface="portal", role="*", page_path="/finance/invoices/")}
        self.assertIn("reconcile", visible)
        self.assertNotIn("export", visible)

    def test_no_path_prefix_means_always_visible(self):
        register_quick_action(
            QuickAction(id="global", label="G", icon="bi-x", href="/g/")
        )
        visible = {a.id for a in actions_for(surface="portal", role="*", page_path="/anything/")}
        self.assertIn("global", visible)

    def test_surface_filter(self):
        register_quick_action(
            QuickAction(
                id="mgr-only",
                label="M",
                icon="bi-x",
                href="/m/",
                surfaces=frozenset({"manager"}),
            )
        )
        self.assertNotIn(
            "mgr-only",
            {a.id for a in actions_for(surface="portal", role="*")},
        )
        self.assertIn(
            "mgr-only",
            {a.id for a in actions_for(surface="manager", role="*")},
        )

    def test_role_filter(self):
        register_quick_action(
            QuickAction(
                id="bursar-only",
                label="B",
                icon="bi-x",
                href="/b/",
                roles=frozenset({"BURSAR"}),
            )
        )
        self.assertNotIn(
            "bursar-only",
            {a.id for a in actions_for(surface="portal", role="TEACHER")},
        )
        self.assertIn(
            "bursar-only",
            {a.id for a in actions_for(surface="portal", role="BURSAR")},
        )

    def test_limit_caps_results(self):
        for i in range(20):
            register_quick_action(
                QuickAction(id=f"a{i}", label=f"A{i}", icon="bi-x", href=f"/a/{i}/", order=i)
            )
        out = actions_for(surface="portal", role="*", limit=5)
        self.assertEqual(len(out), 5)

    def test_jsonable_includes_href(self):
        action = QuickAction(id="x", label="X", icon="bi-x", href="/x/")
        out = action_as_jsonable(action)
        self.assertEqual(out["href"], "/x/")
        self.assertEqual(out["id"], "x")
        self.assertEqual(out["label"], "X")

    def test_actions_as_jsonable_round_trip(self):
        a1 = QuickAction(id="a", label="A", icon="bi-a", href="/a/")
        a2 = QuickAction(id="b", label="B", icon="bi-b", href="/b/")
        out = actions_as_jsonable([a1, a2])
        self.assertEqual(len(out), 2)
        self.assertEqual({entry["id"] for entry in out}, {"a", "b"})
