"""v4.00.91 Wave B — badge resolver + registry tests."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.assist_dock import default_badges  # noqa: F401 — seed
from apps.assist_dock import default_slots  # noqa: F401 — seed
from apps.assist_dock.badges import (
    BADGE_LEVEL_CRITICAL,
    BADGE_LEVEL_INFO,
    BADGE_LEVEL_SUCCESS,
    BADGE_LEVEL_WARNING,
    BadgeSnapshot,
    get_badge_resolver,
    register_badge_resolver,
    resolve_all_badges,
    resolve_badge,
    unregister_badge_resolver,
)
from apps.assist_dock.registry import get_slot


class SnapshotValidationTests(SimpleTestCase):
    def test_level_must_be_valid(self):
        with self.assertRaises(ValueError):
            BadgeSnapshot(count=1, level="bogus")

    def test_count_must_be_non_negative(self):
        with self.assertRaises(ValueError):
            BadgeSnapshot(count=-5)

    def test_jsonable_keys(self):
        snap = BadgeSnapshot(
            count=7, dot=True, level=BADGE_LEVEL_WARNING, tooltip="hi"
        )
        out = snap.as_jsonable()
        self.assertEqual(out["count"], 7)
        self.assertTrue(out["dot"])
        self.assertEqual(out["level"], BADGE_LEVEL_WARNING)
        self.assertEqual(out["tooltip"], "hi")

    def test_dot_only_snapshot_serializes(self):
        snap = BadgeSnapshot(dot=True, level=BADGE_LEVEL_CRITICAL)
        out = snap.as_jsonable()
        self.assertIsNone(out["count"])
        self.assertTrue(out["dot"])


class ResolverRegistrationTests(SimpleTestCase):
    def test_register_and_get(self):
        try:
            sentinel = BadgeSnapshot(count=42, level=BADGE_LEVEL_SUCCESS)

            def resolver(request, *, slot, page_path):  # noqa: ARG001
                return sentinel

            register_badge_resolver("temp-test", resolver)
            self.assertIs(get_badge_resolver("temp-test"), resolver)
        finally:
            unregister_badge_resolver("temp-test")

    def test_register_requires_slot_id(self):
        with self.assertRaises(ValueError):
            register_badge_resolver("", lambda *a, **kw: None)

    def test_register_requires_callable(self):
        with self.assertRaises(TypeError):
            register_badge_resolver("x", "not-callable")

    def test_resolver_exception_swallowed(self):
        def broken(request, *, slot, page_path):  # noqa: ARG001
            raise RuntimeError("boom")

        try:
            register_badge_resolver("broken-test", broken)
            register_temp_slot = mock.Mock(id="broken-test")
            self.assertIsNone(
                resolve_badge(mock.Mock(), slot=register_temp_slot, page_path="/")
            )
        finally:
            unregister_badge_resolver("broken-test")

    def test_resolver_returning_non_snapshot_returns_none(self):
        try:
            register_badge_resolver("dict-test", lambda *a, **kw: {"count": 1})
            self.assertIsNone(
                resolve_badge(mock.Mock(), slot=mock.Mock(id="dict-test"), page_path="/")
            )
        finally:
            unregister_badge_resolver("dict-test")


class MessagesResolverTests(SimpleTestCase):
    def test_anonymous_returns_none(self):
        from apps.assist_dock.default_badges import messages_badge_resolver

        request = mock.Mock()
        request.user = mock.Mock(is_authenticated=False)
        slot = get_slot("messages")
        self.assertIsNone(
            messages_badge_resolver(request, slot=slot, page_path="/")
        )

    def test_returns_none_when_communication_app_missing(self):
        from apps.assist_dock import default_badges

        request = mock.Mock()
        request.user = mock.Mock(is_authenticated=True)
        slot = get_slot("messages")
        with mock.patch.dict(
            "sys.modules", {"apps.communication.models": None}
        ):
            # Force ImportError on the inner import.
            with mock.patch(
                "builtins.__import__", side_effect=ImportError("no module")
            ):
                result = default_badges.messages_badge_resolver(
                    request, slot=slot, page_path="/"
                )
                self.assertIsNone(result)

    def test_returns_count_when_messages_exist(self):
        request = mock.Mock()
        request.user = mock.Mock(is_authenticated=True)
        slot = get_slot("messages")

        # Patch the Message class import + count() to return 5.
        fake_qs = mock.Mock(count=mock.Mock(return_value=5))
        fake_objects = mock.Mock(filter=mock.Mock(return_value=fake_qs))
        fake_message = mock.Mock(objects=fake_objects)
        fake_module = mock.Mock(Message=fake_message)
        with mock.patch.dict(
            "sys.modules", {"apps.communication.models": fake_module}
        ):
            from apps.assist_dock import default_badges

            result = default_badges.messages_badge_resolver(
                request, slot=slot, page_path="/"
            )
            self.assertIsNotNone(result)
            self.assertEqual(result.count, 5)
            self.assertEqual(result.level, BADGE_LEVEL_INFO)
            self.assertTrue(result.dot)

    def test_count_capped_at_99(self):
        request = mock.Mock()
        request.user = mock.Mock(is_authenticated=True)
        slot = get_slot("messages")
        fake_qs = mock.Mock(count=mock.Mock(return_value=500))
        fake_objects = mock.Mock(filter=mock.Mock(return_value=fake_qs))
        fake_module = mock.Mock(Message=mock.Mock(objects=fake_objects))
        with mock.patch.dict("sys.modules", {"apps.communication.models": fake_module}):
            from apps.assist_dock import default_badges

            result = default_badges.messages_badge_resolver(
                request, slot=slot, page_path="/"
            )
            self.assertEqual(result.count, 99)


class ResolveAllBadgesTests(SimpleTestCase):
    def test_returns_dict_keyed_by_slot_id(self):
        try:
            register_badge_resolver(
                "alpha-test",
                lambda *a, **kw: BadgeSnapshot(count=1, level=BADGE_LEVEL_INFO),
            )
            register_badge_resolver(
                "beta-test",
                lambda *a, **kw: BadgeSnapshot(dot=True, level=BADGE_LEVEL_WARNING),
            )

            slots = [mock.Mock(id="alpha-test"), mock.Mock(id="beta-test")]
            result = resolve_all_badges(mock.Mock(), slots=slots, page_path="/")
            self.assertIn("alpha-test", result)
            self.assertIn("beta-test", result)
            self.assertEqual(result["alpha-test"]["count"], 1)
            self.assertEqual(result["beta-test"]["level"], BADGE_LEVEL_WARNING)
        finally:
            unregister_badge_resolver("alpha-test")
            unregister_badge_resolver("beta-test")

    def test_resolver_returning_none_excluded(self):
        try:
            register_badge_resolver("gamma-test", lambda *a, **kw: None)
            slots = [mock.Mock(id="gamma-test")]
            result = resolve_all_badges(mock.Mock(), slots=slots, page_path="/")
            self.assertNotIn("gamma-test", result)
        finally:
            unregister_badge_resolver("gamma-test")
