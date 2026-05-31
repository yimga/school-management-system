"""v4.00.93 Wave C — UserAssistDockPrefs validation + apply tests."""

from __future__ import annotations


from django.test import SimpleTestCase

from apps.assist_dock import default_slots  # noqa: F401 — seed
from apps.assist_dock import power_chips  # noqa: F401 — seed
from apps.assist_dock.models import (
    MAX_HIDDEN,
    MAX_PINNED,
    VALID_DENSITY,
    VALID_SIDE,
    apply_prefs_to_slots,
    coerce_payload,
    default_prefs_payload,
)
from apps.assist_dock.registry import get_slot


class DefaultPayloadTests(SimpleTestCase):
    def test_default_payload_shape(self):
        p = default_prefs_payload()
        for key in ("pinned_order", "hidden_slots", "density", "side", "halo_enabled", "voice_enabled", "version"):
            self.assertIn(key, p)
        self.assertEqual(p["pinned_order"], [])
        self.assertEqual(p["hidden_slots"], [])
        self.assertIn(p["density"], VALID_DENSITY)
        self.assertIn(p["side"], VALID_SIDE)
        self.assertTrue(p["halo_enabled"])
        self.assertFalse(p["voice_enabled"])

    def test_each_call_returns_fresh_dict(self):
        a = default_prefs_payload()
        a["pinned_order"].append("xyz")
        b = default_prefs_payload()
        self.assertEqual(b["pinned_order"], [])


class CoerceTests(SimpleTestCase):
    def test_non_dict_returns_default(self):
        out = coerce_payload(None)
        self.assertEqual(out, default_prefs_payload())

    def test_invalid_density_falls_back(self):
        out = coerce_payload({"density": "bogus"})
        self.assertEqual(out["density"], "cozy")

    def test_invalid_side_falls_back(self):
        out = coerce_payload({"side": "diagonal"})
        self.assertEqual(out["side"], "right")

    def test_pinned_order_truncated(self):
        out = coerce_payload({"pinned_order": [f"x{i}" for i in range(50)]})
        self.assertEqual(len(out["pinned_order"]), MAX_PINNED)

    def test_hidden_slots_truncated(self):
        out = coerce_payload({"hidden_slots": [f"x{i}" for i in range(500)]})
        self.assertEqual(len(out["hidden_slots"]), MAX_HIDDEN)

    def test_unknown_keys_dropped(self):
        out = coerce_payload({"density": "compact", "evil": True, "_hax": 9})
        self.assertNotIn("evil", out)
        self.assertNotIn("_hax", out)
        self.assertEqual(out["density"], "compact")

    def test_halo_and_voice_coerced_to_bool(self):
        out = coerce_payload({"halo_enabled": 0, "voice_enabled": 1})
        self.assertFalse(out["halo_enabled"])
        self.assertTrue(out["voice_enabled"])


class ApplyPrefsToSlotsTests(SimpleTestCase):
    def setUp(self):
        # Re-seed BOTH module so the registry is full regardless of test order.
        import importlib

        from apps.assist_dock import default_slots as ds
        from apps.assist_dock import power_chips as pc

        importlib.reload(ds)
        importlib.reload(pc)

    def test_hidden_slot_filtered(self):
        slots = [get_slot("messages"), get_slot("feedback")]
        payload = default_prefs_payload()
        payload["hidden_slots"] = ["feedback"]
        result = apply_prefs_to_slots(slots, payload)
        ids = [s.id for s in result]
        self.assertEqual(ids, ["messages"])

    def test_pinned_order_promotes_to_front(self):
        slots = [get_slot("messages"), get_slot("ai-copilot"), get_slot("feedback")]
        payload = default_prefs_payload()
        payload["pinned_order"] = ["feedback", "ai-copilot"]
        result = apply_prefs_to_slots(slots, payload)
        ids = [s.id for s in result]
        self.assertEqual(ids[:2], ["feedback", "ai-copilot"])
        self.assertIn("messages", ids)

    def test_empty_slots_returns_empty(self):
        self.assertEqual(apply_prefs_to_slots([], default_prefs_payload()), [])

    def test_no_prefs_returns_order_sorted(self):
        slots = [get_slot("back-to-top"), get_slot("ai-copilot")]
        result = apply_prefs_to_slots(slots, default_prefs_payload())
        self.assertEqual([s.id for s in result], ["ai-copilot", "back-to-top"])


class PowerChipsRegisteredTests(SimpleTestCase):
    def setUp(self):
        # Re-seed BOTH module so reset-style tests can run in any order.
        import importlib

        from apps.assist_dock import default_slots as ds
        from apps.assist_dock import power_chips as pc

        importlib.reload(ds)
        importlib.reload(pc)

    def test_all_six_power_chips_present(self):
        for slot_id in (
            "translate",
            "share-this-view",
            "theme",
            "voice",
            "inspect",
            "impersonate",
        ):
            self.assertIsNotNone(
                get_slot(slot_id), f"power chip {slot_id!r} missing"
            )

    def test_super_only_chips_role_gated(self):
        for slot_id in ("inspect", "impersonate"):
            slot = get_slot(slot_id)
            self.assertEqual(slot.roles, frozenset({"SUPERADMIN"}))

    def test_voice_chip_is_feature_gated(self):
        voice = get_slot("voice")
        self.assertEqual(voice.requires_feature, "voice_assist")
