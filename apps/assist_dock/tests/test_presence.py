"""v4.00.95 Wave E1 — presence tracker tests."""

from __future__ import annotations

import time

from django.test import SimpleTestCase

from apps.assist_dock.presence import (
    PRESENCE_TTL_SECONDS,
    PresenceEntry,
    count_present,
    drop_user,
    entries_as_jsonable,
    heartbeat,
    list_present,
    reset_for_tests,
)


class HeartbeatTests(SimpleTestCase):
    def setUp(self):
        reset_for_tests()

    def tearDown(self):
        reset_for_tests()

    def test_zero_user_id_no_op(self):
        entry = heartbeat(user_id=0, page_path="/x/")
        self.assertIsNone(entry)
        self.assertEqual(count_present(page_path="/x/"), 0)

    def test_blank_page_no_op(self):
        entry = heartbeat(user_id=10, page_path="")
        self.assertIsNone(entry)

    def test_first_heartbeat_records_entry(self):
        entry = heartbeat(
            user_id=10,
            page_path="/portal/",
            display_name="Ada",
            avatar_url="/avatars/ada.png",
        )
        self.assertIsInstance(entry, PresenceEntry)
        self.assertEqual(entry.user_id, 10)
        self.assertEqual(entry.display_name, "Ada")

    def test_refresh_preserves_first_seen(self):
        e1 = heartbeat(user_id=10, page_path="/portal/")
        time.sleep(0.01)
        e2 = heartbeat(user_id=10, page_path="/portal/")
        self.assertEqual(e1.first_seen, e2.first_seen)
        self.assertGreaterEqual(e2.last_seen, e1.last_seen)


class ListPresentTests(SimpleTestCase):
    def setUp(self):
        reset_for_tests()

    def tearDown(self):
        reset_for_tests()

    def test_returns_active_entries(self):
        heartbeat(user_id=10, page_path="/portal/", display_name="A")
        heartbeat(user_id=11, page_path="/portal/", display_name="B")
        out = list_present(page_path="/portal/")
        self.assertEqual({e.user_id for e in out}, {10, 11})

    def test_exclude_user(self):
        heartbeat(user_id=10, page_path="/portal/")
        heartbeat(user_id=11, page_path="/portal/")
        out = list_present(page_path="/portal/", exclude_user_id=10)
        self.assertEqual({e.user_id for e in out}, {11})

    def test_other_page_isolated(self):
        heartbeat(user_id=10, page_path="/portal/")
        heartbeat(user_id=11, page_path="/finance/")
        portal = list_present(page_path="/portal/")
        finance = list_present(page_path="/finance/")
        self.assertEqual({e.user_id for e in portal}, {10})
        self.assertEqual({e.user_id for e in finance}, {11})

    def test_stale_swept_on_read(self):
        from apps.assist_dock import presence as pres

        heartbeat(user_id=10, page_path="/portal/")
        # Mutate the timestamp directly so we don't have to sleep for TTL.
        with pres._LOCK:
            bucket = pres._BY_PAGE["/portal/"]
            old = bucket[10]
            bucket[10] = PresenceEntry(
                user_id=old.user_id,
                display_name=old.display_name,
                avatar_url=old.avatar_url,
                first_seen=old.first_seen - PRESENCE_TTL_SECONDS - 5,
                last_seen=old.last_seen - PRESENCE_TTL_SECONDS - 5,
            )
        out = list_present(page_path="/portal/")
        self.assertEqual(out, [])

    def test_drop_user_purges_all_pages(self):
        heartbeat(user_id=10, page_path="/a/")
        heartbeat(user_id=10, page_path="/b/")
        removed = drop_user(10)
        self.assertEqual(removed, 2)
        self.assertEqual(count_present(page_path="/a/"), 0)
        self.assertEqual(count_present(page_path="/b/"), 0)


class JsonableTests(SimpleTestCase):
    def test_entries_as_jsonable_keys(self):
        entry = PresenceEntry(user_id=10, display_name="A", avatar_url="/x.png")
        out = entries_as_jsonable([entry])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["user_id"], 10)
        self.assertEqual(out[0]["display_name"], "A")
        self.assertEqual(out[0]["avatar_url"], "/x.png")
        self.assertIn("first_seen", out[0])
        self.assertIn("last_seen", out[0])
