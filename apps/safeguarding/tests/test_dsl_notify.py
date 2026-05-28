"""Wave T (v3.97.0 — 2026-05-26) — DSL notification handoff tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.safeguarding.dsl_notify import (
    DSLInboxEntry,
    acknowledge_inbox_entry,
    build_concern_deep_link,
    count_urgent_unacknowledged,
    list_unacknowledged,
    notify_dsl_of_concern,
)


class DeepLinkTests(SimpleTestCase):
    def test_build_deep_link_uses_concern_id(self) -> None:
        url = build_concern_deep_link("abc123")
        self.assertIn("abc123", url)
        self.assertTrue(url.startswith("/school/"))

    def test_blank_concern_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_concern_deep_link("")


class NotifyDslOfConcernTests(SimpleTestCase):
    def _call(self, **overrides):
        kwargs = {
            "current_inbox": None,
            "concern_id": "concern-uuid-1",
            "category_key": "sexual_abuse",
            "category_label": "Sexual abuse",
            "is_urgent": True,
            "submitted_by_user_id": 42,
            "student_id": 7,
            "now_iso": "2026-05-26T10:00:00+00:00",
        }
        kwargs.update(overrides)
        return notify_dsl_of_concern(**kwargs)

    def test_appends_one_entry_to_empty_inbox(self) -> None:
        result = self._call()
        self.assertEqual(len(result.updated_inbox), 1)
        row = result.updated_inbox[0]
        self.assertEqual(row["concern_id"], "concern-uuid-1")
        self.assertEqual(row["is_urgent"], True)
        self.assertIn("concern-uuid-1", row["deep_link_url"])

    def test_preserves_existing_inbox(self) -> None:
        existing = [{"entry_id": "x", "concern_id": "older"}]
        result = self._call(current_inbox=existing)
        self.assertEqual(len(result.updated_inbox), 2)
        # New entry appended last (FIFO order preserved).
        self.assertEqual(result.updated_inbox[0]["concern_id"], "older")
        self.assertEqual(result.updated_inbox[1]["concern_id"], "concern-uuid-1")

    def test_fifo_cap_trims_oldest(self) -> None:
        # 200 is the cap; 201 entries -> oldest dropped.
        seed = [{"entry_id": f"e{i}", "concern_id": f"old-{i}"} for i in range(200)]
        result = self._call(current_inbox=seed)
        self.assertEqual(len(result.updated_inbox), 200)
        # First-in (entry e0) is gone; last entry is the new one.
        ids = [row.get("entry_id") for row in result.updated_inbox]
        self.assertNotIn("e0", ids)
        self.assertEqual(result.updated_inbox[-1]["concern_id"], "concern-uuid-1")

    def test_narrative_text_never_stored(self) -> None:
        # The notifier MUST NOT accept or echo narrative bodies; the deep
        # link is the only path to PII.
        result = self._call()
        row = result.updated_inbox[0]
        for key in row.keys():
            self.assertNotIn("narrative", key)
            self.assertNotIn("body", key)
            self.assertNotIn("description", key)

    def test_returns_typed_entry(self) -> None:
        result = self._call()
        self.assertIsInstance(result.entry, DSLInboxEntry)
        self.assertEqual(result.entry.concern_id, "concern-uuid-1")
        self.assertTrue(result.entry.is_urgent)

    def test_blank_concern_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            self._call(concern_id="")

    def test_blank_category_raises(self) -> None:
        with self.assertRaises(ValueError):
            self._call(category_key="")

    def test_invalid_user_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            self._call(submitted_by_user_id=0)

    def test_invalid_student_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            self._call(student_id=-1)

    def test_label_falls_back_to_key(self) -> None:
        result = self._call(category_label="")
        self.assertEqual(result.updated_inbox[0]["category_label"], "sexual_abuse")


class AcknowledgeTests(SimpleTestCase):
    def _seeded_inbox(self) -> list[dict]:
        return notify_dsl_of_concern(
            current_inbox=None,
            concern_id="c1",
            category_key="neglect",
            category_label="Neglect",
            is_urgent=False,
            submitted_by_user_id=10,
            student_id=11,
            now_iso="2026-05-26T10:00:00+00:00",
        ).updated_inbox

    def test_ack_sets_timestamp_and_actor(self) -> None:
        inbox = self._seeded_inbox()
        entry_id = inbox[0]["entry_id"]
        updated = acknowledge_inbox_entry(
            current_inbox=inbox,
            entry_id=entry_id,
            acknowledged_by_user_id=99,
            now_iso="2026-05-26T11:00:00+00:00",
        )
        self.assertEqual(updated[0]["acknowledged_by_user_id"], 99)
        self.assertEqual(updated[0]["acknowledged_at_iso"], "2026-05-26T11:00:00+00:00")

    def test_ack_is_idempotent_first_actor_wins(self) -> None:
        inbox = self._seeded_inbox()
        entry_id = inbox[0]["entry_id"]
        once = acknowledge_inbox_entry(
            current_inbox=inbox,
            entry_id=entry_id,
            acknowledged_by_user_id=99,
            now_iso="2026-05-26T11:00:00+00:00",
        )
        twice = acknowledge_inbox_entry(
            current_inbox=once,
            entry_id=entry_id,
            acknowledged_by_user_id=12,  # different DSL clicks later
            now_iso="2026-05-26T12:00:00+00:00",
        )
        # First actor + first timestamp preserved.
        self.assertEqual(twice[0]["acknowledged_by_user_id"], 99)
        self.assertEqual(twice[0]["acknowledged_at_iso"], "2026-05-26T11:00:00+00:00")

    def test_ack_unknown_entry_is_noop(self) -> None:
        inbox = self._seeded_inbox()
        updated = acknowledge_inbox_entry(
            current_inbox=inbox,
            entry_id="does-not-exist",
            acknowledged_by_user_id=99,
        )
        self.assertEqual(updated[0].get("acknowledged_at_iso", ""), "")

    def test_blank_entry_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            acknowledge_inbox_entry(
                current_inbox=[], entry_id="", acknowledged_by_user_id=1,
            )

    def test_invalid_actor_raises(self) -> None:
        with self.assertRaises(ValueError):
            acknowledge_inbox_entry(
                current_inbox=[], entry_id="x", acknowledged_by_user_id=0,
            )


class InboxQueryTests(SimpleTestCase):
    def _seed(self, urgent_count: int, non_urgent_count: int) -> list[dict]:
        inbox: list[dict] = []
        for i in range(urgent_count):
            inbox = notify_dsl_of_concern(
                current_inbox=inbox,
                concern_id=f"urgent-{i}",
                category_key="sexual_abuse",
                category_label="Sexual abuse",
                is_urgent=True,
                submitted_by_user_id=1,
                student_id=2,
            ).updated_inbox
        for i in range(non_urgent_count):
            inbox = notify_dsl_of_concern(
                current_inbox=inbox,
                concern_id=f"low-{i}",
                category_key="other",
                category_label="Other",
                is_urgent=False,
                submitted_by_user_id=1,
                student_id=2,
            ).updated_inbox
        return inbox

    def test_list_unack_excludes_acked(self) -> None:
        inbox = self._seed(urgent_count=2, non_urgent_count=1)
        entry_id = inbox[0]["entry_id"]
        inbox = acknowledge_inbox_entry(
            current_inbox=inbox, entry_id=entry_id, acknowledged_by_user_id=1,
        )
        self.assertEqual(len(list_unacknowledged(inbox)), 2)

    def test_count_urgent_unack(self) -> None:
        inbox = self._seed(urgent_count=3, non_urgent_count=5)
        self.assertEqual(count_urgent_unacknowledged(inbox), 3)
        # Ack one urgent — count drops to 2.
        urgent_id = [r for r in inbox if r["is_urgent"]][0]["entry_id"]
        inbox = acknowledge_inbox_entry(
            current_inbox=inbox, entry_id=urgent_id, acknowledged_by_user_id=1,
        )
        self.assertEqual(count_urgent_unacknowledged(inbox), 2)

    def test_count_on_empty_inbox(self) -> None:
        self.assertEqual(count_urgent_unacknowledged(None), 0)
        self.assertEqual(count_urgent_unacknowledged([]), 0)
        self.assertEqual(list_unacknowledged(None), [])
