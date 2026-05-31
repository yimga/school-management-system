"""v4.00.94 Wave D — AI view endpoint tests (action invoke, insights)."""

from __future__ import annotations

import json
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.assist_dock import default_ai_actions  # noqa: F401 — seed
from apps.assist_dock.insights import (
    Insight,
    INSIGHT_WARNING,
    push_insight,
    reset_for_tests,
)
from apps.assist_dock.views_ai import (
    clear_insight_view,
    invoke_ai_action_view,
    list_ai_actions,
    list_insights_view,
)


def _unwrap(func, depth=4):
    """Strip ``functools.wraps`` decorator chain."""
    for _ in range(depth):
        inner = getattr(func, "__wrapped__", None)
        if inner is None:
            return func
        func = inner
    return func


class ListAIActionsTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_returns_seeded_actions(self):
        view = _unwrap(list_ai_actions)
        req = self.rf.get("/assist-dock/ai/actions.json")
        req.user = mock.Mock(is_authenticated=True, is_active=True, pk=1)
        response = view(req)
        payload = json.loads(response.content)
        ids = {a["id"] for a in payload["actions"]}
        for expected in ("summarize", "explain", "draft", "translate"):
            self.assertIn(expected, ids)


class InvokeAIActionViewTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _user(self):
        return mock.Mock(
            is_authenticated=True, is_active=True, pk=1, active_role="TEACHER"
        )

    def test_bad_json_returns_400(self):
        view = _unwrap(invoke_ai_action_view)
        req = self.rf.post(
            "/assist-dock/ai/summarize/",
            data=b"not-json",
            content_type="application/json",
        )
        req.user = self._user()
        response = view(req, action_id="summarize")
        self.assertEqual(response.status_code, 400)

    def test_oversize_returns_400(self):
        view = _unwrap(invoke_ai_action_view)
        big = b"x" * 20000
        req = self.rf.post(
            "/assist-dock/ai/summarize/",
            data=big,
            content_type="application/json",
        )
        req.user = self._user()
        response = view(req, action_id="summarize")
        self.assertEqual(response.status_code, 400)

    def test_non_object_body_returns_400(self):
        view = _unwrap(invoke_ai_action_view)
        req = self.rf.post(
            "/assist-dock/ai/summarize/",
            data=b'["a","b"]',
            content_type="application/json",
        )
        req.user = self._user()
        response = view(req, action_id="summarize")
        self.assertEqual(response.status_code, 400)

    def test_unknown_action_returns_503(self):
        view = _unwrap(invoke_ai_action_view)
        req = self.rf.post(
            "/assist-dock/ai/nope/",
            data=b"{}",
            content_type="application/json",
        )
        req.user = self._user()
        response = view(req, action_id="nope")
        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.content)
        self.assertEqual(payload["error"], "unknown_action")

    def test_success_returns_200_envelope(self):
        view = _unwrap(invoke_ai_action_view)
        req = self.rf.post(
            "/assist-dock/ai/summarize/",
            data=json.dumps({"page_path": "/portal/"}).encode("utf-8"),
            content_type="application/json",
        )
        req.user = self._user()
        with mock.patch(
            "services.ai_helpers.invoke_with_request",
            return_value=("3 bullets here", {"tier": "ollama"}),
        ):
            response = view(req, action_id="summarize")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["text"], "3 bullets here")


class InsightsViewTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()
        reset_for_tests()

    def tearDown(self):
        reset_for_tests()

    def test_list_anonymous_returns_empty(self):
        view = _unwrap(list_insights_view)
        req = self.rf.get("/assist-dock/insights.json")
        req.user = mock.Mock(is_authenticated=False, pk=None)
        response = view(req)
        payload = json.loads(response.content)
        self.assertEqual(payload["insights"], [])

    def test_list_returns_user_insights(self):
        push_insight(99, Insight(id="alpha", title="A", level=INSIGHT_WARNING))
        push_insight(99, Insight(id="beta", title="B"))
        view = _unwrap(list_insights_view)
        req = self.rf.get("/assist-dock/insights.json")
        req.user = mock.Mock(is_authenticated=True, is_active=True, pk=99)
        response = view(req)
        payload = json.loads(response.content)
        ids = {i["id"] for i in payload["insights"]}
        self.assertEqual(ids, {"alpha", "beta"})

    def test_list_filters_by_page(self):
        push_insight(99, Insight(id="g", title="g"))
        push_insight(
            99, Insight(id="l", title="l", page_path="/finance/")
        )
        view = _unwrap(list_insights_view)
        req = self.rf.get("/assist-dock/insights.json?page=/portal/")
        req.user = mock.Mock(is_authenticated=True, pk=99)
        response = view(req)
        payload = json.loads(response.content)
        ids = {i["id"] for i in payload["insights"]}
        self.assertEqual(ids, {"g"})

    def test_clear_view_removes_insight(self):
        push_insight(99, Insight(id="alpha", title="A"))
        view = _unwrap(clear_insight_view)
        req = self.rf.post(
            "/assist-dock/insights/clear/",
            data=json.dumps({"insight_id": "alpha"}).encode("utf-8"),
            content_type="application/json",
        )
        req.user = mock.Mock(is_authenticated=True, pk=99)
        response = view(req)
        payload = json.loads(response.content)
        self.assertTrue(payload["removed"])

    def test_clear_view_bad_body(self):
        view = _unwrap(clear_insight_view)
        req = self.rf.post(
            "/assist-dock/insights/clear/",
            data=b"not-json",
            content_type="application/json",
        )
        req.user = mock.Mock(is_authenticated=True, pk=99)
        response = view(req)
        self.assertEqual(response.status_code, 400)

    def test_clear_view_missing_id(self):
        view = _unwrap(clear_insight_view)
        req = self.rf.post(
            "/assist-dock/insights/clear/",
            data=b"{}",
            content_type="application/json",
        )
        req.user = mock.Mock(is_authenticated=True, pk=99)
        response = view(req)
        self.assertEqual(response.status_code, 400)


class AICopilotBadgeResolverTests(SimpleTestCase):
    def setUp(self):
        reset_for_tests()

    def tearDown(self):
        reset_for_tests()

    def test_no_insights_returns_none(self):
        from apps.assist_dock.default_badges import ai_copilot_badge_resolver

        request = mock.Mock()
        request.user = mock.Mock(is_authenticated=True, pk=10)
        slot = mock.Mock(id="ai-copilot")
        self.assertIsNone(
            ai_copilot_badge_resolver(request, slot=slot, page_path="/")
        )

    def test_insights_promote_level_to_critical(self):
        from apps.assist_dock.default_badges import ai_copilot_badge_resolver

        push_insight(10, Insight(id="info1", title="x"))
        push_insight(10, Insight(id="crit1", title="!", level="critical"))
        request = mock.Mock()
        request.user = mock.Mock(is_authenticated=True, pk=10)
        slot = mock.Mock(id="ai-copilot")
        snap = ai_copilot_badge_resolver(request, slot=slot, page_path="/")
        self.assertIsNotNone(snap)
        self.assertEqual(snap.count, 2)
        self.assertEqual(snap.level, "critical")
