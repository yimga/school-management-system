"""Tests for the platform SOTs introduced in v4.01.02.

Covers:
- `keyboard_shortcuts` — global + lux registry + surface registration; conflict
  detection; cheatsheet payload shape.
- `sidebar_registry` — role-scoped, shell-scoped filtering; idempotent
  registration; deterministic order.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime import keyboard_shortcuts as ks
from apps.platform_runtime import sidebar_registry as sr


class KeyboardShortcutsSOTTests(SimpleTestCase):
    def test_global_shortcuts_present(self):
        shortcuts = ks.iter_all_shortcuts()
        actions = {s.action for s in shortcuts if s.scope == "global"}
        self.assertIn("OPEN_COMMAND_CONSOLE", actions)
        self.assertIn("OPEN_KEYBOARD_HELP", actions)
        self.assertIn("CLOSE_TOP_OVERLAY", actions)

    def test_lux_tier_shortcuts_loaded_from_registry_json(self):
        shortcuts = ks.iter_all_shortcuts()
        tier_scopes = {s.scope for s in shortcuts if s.scope.startswith("tier:")}
        self.assertEqual(
            tier_scopes,
            {"tier:FINANCIAL_LEDGER", "tier:ACADEMIC_MATRIX", "tier:OPERATOR_SHELL"},
        )

    def test_no_global_conflicts_on_clean_registry(self):
        conflicts = ks.detect_conflicts()
        global_conflicts = [c for c in conflicts if "@global" in c[0]]
        self.assertEqual(global_conflicts, [])

    def test_surface_registration_isolates_chord_reuse(self):
        ks.register_surface(
            "/gradebook/",
            [
                {
                    "chord": "Mod+s",
                    "action": "SAVE_GRADEBOOK_ROW",
                    "label": "Save current row",
                }
            ],
        )
        ks.register_surface(
            "/finance/invoices/",
            [
                {
                    "chord": "Mod+s",
                    "action": "SAVE_INVOICE_DRAFT",
                    "label": "Save invoice draft",
                }
            ],
        )
        conflicts = ks.detect_conflicts()
        same_scope_conflicts = [
            c for c in conflicts if "Mod+s@surface:/gradebook/" == c[0]
        ]
        self.assertEqual(same_scope_conflicts, [])

    def test_cheatsheet_payload_shape(self):
        payload = ks.cheatsheet_payload()
        self.assertIn("scopes", payload)
        self.assertIn("global", payload["scopes"])
        for entries in payload["scopes"].values():
            for e in entries:
                self.assertIn("chord", e)
                self.assertIn("action", e)
                self.assertIn("label", e)


class SidebarRegistrySOTTests(SimpleTestCase):
    def test_seed_registered(self):
        items = sr.all_items()
        keys = {it.key for it in items}
        self.assertIn("dashboard", keys)
        self.assertIn("operator_console", keys)
        self.assertIn("settings", keys)

    def test_role_scoping_parent_does_not_see_admin(self):
        items = sr.for_shell(sr.SHELL_PORTAL, ["PARENT"])
        keys = {it.key for it in items}
        self.assertIn("dashboard", keys)
        self.assertNotIn("manage_school", keys)
        self.assertNotIn("operator_console", keys)

    def test_role_scoping_proprietor_sees_management(self):
        items = sr.for_shell(sr.SHELL_PORTAL, ["PROPRIETOR"])
        keys = {it.key for it in items}
        self.assertIn("manage_school", keys)
        self.assertIn("marketplace", keys)

    def test_shell_scoping_marketing_empty_by_default(self):
        items = sr.for_shell(sr.SHELL_MARKETING, ["PARENT", "ADMIN", "PROPRIETOR"])
        self.assertEqual(items, [])

    def test_deterministic_order(self):
        items = sr.for_shell(sr.SHELL_PORTAL, ["ADMIN"])
        orders = [it.order for it in items]
        self.assertEqual(orders, sorted(orders))

    def test_register_is_idempotent_last_wins(self):
        sr.register(
            sr.NavItem(
                key="dashboard",
                label="Dashboard (overridden)",
                icon="bi-house",
                url_name="portal:home",
                roles=("PARENT",),
                shells=(sr.SHELL_PORTAL,),
                order=5,
            )
        )
        items = [it for it in sr.all_items() if it.key == "dashboard"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].label, "Dashboard (overridden)")

    def test_studio_focus_shell_phase1_migration(self):
        """v4.01.04: Studio Focus sidebar (Phase 1 of 4-phase migration)."""
        items = sr.for_shell(sr.SHELL_STUDIO_FOCUS, ["PROPRIETOR"])
        keys = [it.key for it in items]
        self.assertIn("studio_overview", keys)
        self.assertIn("studio_experience", keys)
        self.assertIn("studio_automation", keys)
        self.assertIn("studio_output", keys)
        self.assertIn("studio_launch", keys)
        self.assertIn("studio_control", keys)
        self.assertIn("studio_command_center", keys)
        self.assertIn("studio_schools", keys)
        for item in items:
            self.assertEqual(item.urlconf, "config.manager_urls")
            self.assertIn(item.section, ("modes", "shortcuts"))

    def test_studio_focus_blocks_non_proprietor(self):
        items = sr.for_shell(sr.SHELL_STUDIO_FOCUS, ["PARENT", "STUDENT", "TEACHER"])
        keys = [it.key for it in items]
        self.assertNotIn("studio_overview", keys)
        self.assertNotIn("studio_command_center", keys)
