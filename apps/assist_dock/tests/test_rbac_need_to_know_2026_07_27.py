"""RBAC need-to-know gating for the copilot / Tools rails (2026-07-27).

Conservative model: every role keeps the universal tools (help, messages,
theme, keyboard shortcuts, back-to-top, translate, help center, report issue,
own-account security posture, AI copilot), while admin/staff-tier tools
(cross-entity command search, control-plane context drawer, operator presence,
live cursors) are hidden from FAMILY_PORTAL_ROLES (parent / student / employer).

Also covers the profile-aware fix: an admin/staff user previewing AS a parent
(session ``active_portal_role`` hat) is resolved to the family role, so their
rail loses the admin-tier chips even though their account role is staff.
"""

from __future__ import annotations

from unittest import mock

from django.test import RequestFactory, SimpleTestCase

# Import every slot module so the process-global registry is fully seeded
# (mirrors AssistDockConfig.ready order).
from apps.assist_dock import (  # noqa: F401 — seed registry
    default_slots,
    operator_tools_slots,
    power_chips,
    tenant_tools_slots,
)
from apps.assist_dock.context_processors import _resolve_role
from apps.assist_dock.registry import (
    FAMILY_PORTAL_ROLES,
    SURFACE_PORTAL,
    AssistDockSlot,
    get_slots_for,
    register_slot,
    unregister_slot,
)

# Tools that must NEVER surface for a family role (need-to-know).
ADMIN_TIER_SLOTS = frozenset(
    {"tenant-command", "context", "presence", "live-cursors"}
)
# Tools every role keeps.
UNIVERSAL_SLOTS = frozenset(
    {
        "ai-copilot",
        "messages",
        "help",
        "back-to-top",
        "theme",
        "translate",
        "keyboard-shortcuts",
        "tenant-kb",
        "tenant-support",
        "security-posture",
    }
)


def _ids(surface, role):
    return {slot.id for slot in get_slots_for(surface=surface, role=role)}


class RailRoleGatingTests(SimpleTestCase):
    def test_family_roles_never_see_admin_tier_tools(self):
        for role in sorted(FAMILY_PORTAL_ROLES):
            ids = _ids(SURFACE_PORTAL, role)
            leaked = ADMIN_TIER_SLOTS & ids
            self.assertFalse(
                leaked, f"{role} leaked admin-tier tools: {sorted(leaked)}"
            )

    def test_family_roles_keep_universal_tools(self):
        # Feature-flagged / manager-only slots aside, the family portal rail must
        # still carry the everyday helpers. include_hidden=True skips the
        # feature-flag filter so ai-copilot is present regardless of flag here.
        for role in sorted(FAMILY_PORTAL_ROLES):
            ids = {
                s.id
                for s in get_slots_for(
                    surface=SURFACE_PORTAL, role=role, include_hidden=True
                )
            }
            for expected in ("help", "messages", "back-to-top", "tenant-kb", "theme"):
                self.assertIn(
                    expected, ids, f"{role} lost universal tool {expected}"
                )

    def test_staff_and_admin_keep_admin_tier_tools(self):
        for role in ("TEACHER", "ADMIN", "PRINCIPAL", "BURSAR", "IT_ADMIN"):
            ids = _ids(SURFACE_PORTAL, role)
            missing = ADMIN_TIER_SLOTS - ids
            self.assertFalse(
                missing, f"{role} should keep admin-tier tools, missing {sorted(missing)}"
            )

    def test_denylist_is_registry_level(self):
        # A synthetic slot with roles={"*"} but a PARENT denylist is filtered.
        register_slot(
            AssistDockSlot(
                id="__rbac-probe__",
                label="probe",
                icon="bi-bug",
                hidden_for_roles=frozenset({"PARENT"}),
            )
        )
        try:
            self.assertNotIn("__rbac-probe__", _ids(SURFACE_PORTAL, "PARENT"))
            self.assertIn("__rbac-probe__", _ids(SURFACE_PORTAL, "TEACHER"))
            # Wildcard caller is exempt from the denylist.
            self.assertIn(
                "__rbac-probe__",
                {s.id for s in get_slots_for(surface=SURFACE_PORTAL, role="*")},
            )
        finally:
            unregister_slot("__rbac-probe__")


class EffectiveHatResolutionTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _staff_user(self):
        return mock.Mock(
            is_authenticated=True,
            is_superuser=False,
            is_staff=True,
            active_role="ADMIN",
            primary_role="ADMIN",
            role="ADMIN",
        )

    def test_admin_previewing_as_parent_resolves_to_parent(self):
        req = self.rf.get("/portal/dashboard/")
        req.user = self._staff_user()
        req.session = {"active_portal_role": "parent"}  # lower-case → normalized
        self.assertEqual(_resolve_role(req), "PARENT")

    def test_no_hat_falls_back_to_primary_role(self):
        req = self.rf.get("/portal/dashboard/")
        req.user = self._staff_user()
        req.session = {}
        self.assertEqual(_resolve_role(req), "ADMIN")

    def test_admin_hat_gets_admin_tier_but_parent_hat_does_not(self):
        # Same staff account, two different hats → two different rails.
        admin_req = self.rf.get("/portal/dashboard/")
        admin_req.user = self._staff_user()
        admin_req.session = {}
        parent_req = self.rf.get("/portal/dashboard/")
        parent_req.user = self._staff_user()
        parent_req.session = {"active_portal_role": "PARENT"}

        admin_ids = _ids(SURFACE_PORTAL, _resolve_role(admin_req))
        parent_ids = _ids(SURFACE_PORTAL, _resolve_role(parent_req))
        self.assertTrue(ADMIN_TIER_SLOTS <= admin_ids)
        self.assertFalse(ADMIN_TIER_SLOTS & parent_ids)
