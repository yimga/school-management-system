"""v4.00.91 — assist_dock registry shape, filter, and serialization tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.assist_dock import default_slots  # noqa: F401 — seed registry
from apps.assist_dock.registry import (
    SOURCE_DOM_ADOPT,
    SOURCE_EXTERNAL,
    SOURCE_REGISTRY,
    SURFACE_ADMIN,
    SURFACE_ANY,
    SURFACE_MANAGER,
    SURFACE_PORTAL,
    AssistDockSlot,
    all_slots,
    get_slot,
    get_slots_for,
    register_slot,
    replace_slot,
    reset_registry_for_tests,
    slot_as_jsonable,
    slots_as_jsonable,
    unregister_slot,
)


class SlotValidationTests(SimpleTestCase):
    def test_id_required(self):
        with self.assertRaises(ValueError):
            AssistDockSlot(id="", label="X", icon="bi-x")

    def test_source_must_be_valid(self):
        with self.assertRaises(ValueError):
            AssistDockSlot(id="x", label="X", icon="bi-x", source="bogus")

    def test_dom_adopt_requires_selector(self):
        with self.assertRaises(ValueError):
            AssistDockSlot(
                id="x", label="X", icon="bi-x", source=SOURCE_DOM_ADOPT
            )

    def test_external_requires_href(self):
        with self.assertRaises(ValueError):
            AssistDockSlot(
                id="x", label="X", icon="bi-x", source=SOURCE_EXTERNAL
            )

    def test_valid_registry_slot_constructs(self):
        slot = AssistDockSlot(id="x", label="X", icon="bi-x")
        self.assertEqual(slot.source, SOURCE_REGISTRY)
        self.assertIn(SURFACE_ANY, slot.surfaces)
        self.assertIn("*", slot.roles)


class DefaultRegistrySeedTests(SimpleTestCase):
    """The six legacy chips must seed at import-time."""

    def test_six_default_slots_present(self):
        for slot_id in (
            "ai-copilot",
            "messages",
            "feedback",
            "help",
            "context",
            "back-to-top",
        ):
            slot = get_slot(slot_id)
            self.assertIsNotNone(slot, f"missing default slot {slot_id!r}")
            self.assertEqual(slot.source, SOURCE_DOM_ADOPT)
            self.assertTrue(slot.adopt_selector)

    def test_default_slots_visible_on_all_surfaces(self):
        for surface in (SURFACE_PORTAL, SURFACE_MANAGER, SURFACE_ADMIN):
            visible = {s.id for s in get_slots_for(surface=surface)}
            # Legacy chips without feature gates appear in the default list.
            self.assertIn("messages", visible)
            gated = {s.id for s in get_slots_for(surface=surface, include_hidden=True)}
            self.assertIn("ai-copilot", gated)
            self.assertIn("messages", visible)
            self.assertIn("back-to-top", visible)

    def test_primary_row_chips_are_pinned(self):
        ai = get_slot("ai-copilot")
        msgs = get_slot("messages")
        feedback = get_slot("feedback")
        self.assertTrue(ai.pinned_default)
        self.assertTrue(msgs.pinned_default)
        self.assertFalse(feedback.pinned_default)


class FilterTests(SimpleTestCase):
    def test_role_star_matches_all_roles(self):
        slot = get_slot("ai-copilot")
        self.assertIn("*", slot.roles)
        teacher_gated = {s.id for s in get_slots_for(surface=SURFACE_PORTAL, role="TEACHER", include_hidden=True)}
        anon_gated = {s.id for s in get_slots_for(surface=SURFACE_PORTAL, role="anonymous", include_hidden=True)}
        self.assertIn("ai-copilot", teacher_gated)
        self.assertIn("ai-copilot", anon_gated)

    def test_specific_role_filter_rejects_non_match(self):
        try:
            register_slot(
                AssistDockSlot(
                    id="super-only-test",
                    label="super",
                    icon="bi-x",
                    roles=frozenset({"SUPERADMIN"}),
                )
            )
            visible = {s.id for s in get_slots_for(surface=SURFACE_PORTAL, role="TEACHER")}
            self.assertNotIn("super-only-test", visible)
            visible_super = {
                s.id for s in get_slots_for(surface=SURFACE_PORTAL, role="SUPERADMIN")
            }
            self.assertIn("super-only-test", visible_super)
        finally:
            unregister_slot("super-only-test")

    def test_surface_filter_excludes_other_surfaces(self):
        try:
            register_slot(
                AssistDockSlot(
                    id="manager-only-test",
                    label="mgr",
                    icon="bi-x",
                    surfaces=frozenset({SURFACE_MANAGER}),
                )
            )
            self.assertNotIn(
                "manager-only-test",
                {s.id for s in get_slots_for(surface=SURFACE_PORTAL)},
            )
            self.assertIn(
                "manager-only-test",
                {s.id for s in get_slots_for(surface=SURFACE_MANAGER)},
            )
        finally:
            unregister_slot("manager-only-test")

    def test_order_is_ascending(self):
        slots = get_slots_for(surface=SURFACE_PORTAL)
        orders = [s.order for s in slots]
        self.assertEqual(orders, sorted(orders))

    def test_feature_gated_excluded_by_default_included_when_hidden(self):
        try:
            register_slot(
                AssistDockSlot(
                    id="gated-test",
                    label="gated",
                    icon="bi-x",
                    requires_feature="beta_dock",
                )
            )
            self.assertNotIn(
                "gated-test", {s.id for s in get_slots_for(surface=SURFACE_PORTAL)}
            )
            self.assertIn(
                "gated-test",
                {s.id for s in get_slots_for(surface=SURFACE_PORTAL, include_hidden=True)},
            )
        finally:
            unregister_slot("gated-test")


class SerializationTests(SimpleTestCase):
    def test_jsonable_keys_deterministic(self):
        slot = get_slot("ai-copilot")
        out = slot_as_jsonable(slot)
        # frozensets serialized as sorted lists, lazy gettext coerced to str.
        self.assertEqual(out["id"], "ai-copilot")
        self.assertEqual(out["icon"], "bi-stars")
        self.assertIsInstance(out["label"], str)
        self.assertIsInstance(out["surfaces"], list)
        self.assertEqual(out["surfaces"], sorted(out["surfaces"]))
        self.assertIsInstance(out["roles"], list)

    def test_slots_as_jsonable_round_trips(self):
        all_jsonable = slots_as_jsonable(all_slots())
        self.assertGreaterEqual(len(all_jsonable), 6)
        ids = {entry["id"] for entry in all_jsonable}
        self.assertIn("ai-copilot", ids)
        self.assertIn("back-to-top", ids)


class ReplaceSlotTests(SimpleTestCase):
    def test_replace_returns_new_slot_with_changes(self):
        original = get_slot("feedback")
        self.assertIsNotNone(original)
        original_order = original.order
        try:
            new_slot = replace_slot("feedback", order=999, pinned_default=True)
            self.assertIsNotNone(new_slot)
            self.assertEqual(new_slot.order, 999)
            self.assertTrue(new_slot.pinned_default)
            # Original frozensets / labels preserved by dataclass.replace.
            self.assertEqual(new_slot.adopt_selector, original.adopt_selector)
        finally:
            replace_slot("feedback", order=original_order, pinned_default=False)

    def test_replace_unknown_returns_none(self):
        self.assertIsNone(replace_slot("does-not-exist", order=1))


class ResetTests(SimpleTestCase):
    def test_reset_clears_then_reseed(self):
        before = len(all_slots())
        self.assertGreaterEqual(before, 6)
        reset_registry_for_tests()
        self.assertEqual(len(all_slots()), 0)
        # Re-import the seed modules so the registry returns to full state
        # for any downstream test in the class — both default_slots AND
        # power_chips contribute to the canonical seeded count.
        import importlib

        from apps.assist_dock import default_slots as ds
        from apps.assist_dock import power_chips as pc

        importlib.reload(ds)
        importlib.reload(pc)
        after = len(all_slots())
        # 6 default + 6 power chips = 12; allow >= so future seed modules don't
        # break this assertion.
        self.assertGreaterEqual(after, 12)
