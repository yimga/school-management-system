"""v4.00.94 Wave D — proactive insights ring tests."""

from __future__ import annotations

import time

from django.test import SimpleTestCase

from apps.assist_dock.insights import (
    INSIGHT_CRITICAL,
    INSIGHT_INFO,
    INSIGHT_TTL_SECONDS,
    INSIGHT_WARNING,
    MAX_PER_USER,
    Insight,
    clear_insight,
    count_insights,
    insight_as_jsonable,
    list_insights,
    push_insight,
    reset_for_tests,
)


class InsightValidationTests(SimpleTestCase):
    def test_id_required(self):
        with self.assertRaises(ValueError):
            Insight(id="", title="x")

    def test_invalid_level(self):
        with self.assertRaises(ValueError):
            Insight(id="x", title="x", level="bogus")

    def test_default_not_expired(self):
        i = Insight(id="x", title="x")
        self.assertFalse(i.is_expired())

    def test_explicit_expiry_in_past(self):
        i = Insight(id="x", title="x", expires_at=time.time() - 1)
        self.assertTrue(i.is_expired())


class QueueTests(SimpleTestCase):
    def setUp(self):
        reset_for_tests()

    def tearDown(self):
        reset_for_tests()

    def test_push_and_list(self):
        push_insight(42, Insight(id="a", title="A"))
        push_insight(42, Insight(id="b", title="B"))
        items = list_insights(42)
        self.assertEqual({i.id for i in items}, {"a", "b"})

    def test_idempotent_replace_by_id(self):
        push_insight(42, Insight(id="a", title="first"))
        push_insight(42, Insight(id="a", title="second"))
        items = list_insights(42)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "second")

    def test_page_path_filter(self):
        push_insight(42, Insight(id="global", title="g"))
        push_insight(42, Insight(id="local", title="l", page_path="/finance/"))
        all_items = list_insights(42)
        finance_items = list_insights(42, page_path="/finance/")
        portal_items = list_insights(42, page_path="/portal/")
        self.assertEqual(len(all_items), 2)
        self.assertEqual({i.id for i in finance_items}, {"global", "local"})
        self.assertEqual({i.id for i in portal_items}, {"global"})

    def test_max_per_user_cap(self):
        for i in range(MAX_PER_USER + 10):
            push_insight(42, Insight(id=f"n{i}", title=f"N{i}"))
        items = list_insights(42)
        self.assertLessEqual(len(items), MAX_PER_USER)

    def test_clear_removes_specific_insight(self):
        push_insight(42, Insight(id="a", title="A"))
        push_insight(42, Insight(id="b", title="B"))
        self.assertTrue(clear_insight(42, "a"))
        items = list_insights(42)
        self.assertEqual({i.id for i in items}, {"b"})

    def test_clear_unknown_returns_false(self):
        self.assertFalse(clear_insight(42, "nope"))

    def test_expired_swept_on_read(self):
        old = Insight(id="old", title="old", expires_at=time.time() - 1)
        push_insight(42, old)
        items = list_insights(42)
        self.assertEqual(items, [])

    def test_count_matches_list(self):
        push_insight(42, Insight(id="a", title="A"))
        push_insight(42, Insight(id="b", title="B"))
        self.assertEqual(count_insights(42), 2)

    def test_anonymous_user_id_returns_empty(self):
        self.assertEqual(list_insights(0), [])
        self.assertEqual(count_insights(0), 0)

    def test_jsonable_keys(self):
        i = Insight(id="a", title="A", body="b", level=INSIGHT_CRITICAL)
        out = insight_as_jsonable(i)
        self.assertEqual(out["id"], "a")
        self.assertEqual(out["level"], INSIGHT_CRITICAL)
