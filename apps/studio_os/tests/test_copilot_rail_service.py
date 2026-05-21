"""Studio OS Co-pilot Rail service contract (v3.53.1, 2026-05-21).

Asserts:
  - build_context_snapshot returns hashed slug + correct mode + posture
  - generate_insights cloud path -> source="cloud" (mocked invoke_with_request)
  - generate_insights rules fallback -> source="rules" (AI unreachable / None)
  - generate_insights always returns exactly N
  - resolve_quick_actions filters by surface and respects tenant + role
  - Cross-tenant safety: snapshot for school A never leaks school B references
  - No PII / slugs in logger calls (assertLogs)
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.studio_os.copilot_rail_service import (
    CopilotContextSnapshot,
    CopilotInsight,
    MAX_QUICK_ACTIONS,
    build_context_snapshot,
    build_rail_payload,
    generate_insights,
    resolve_quick_actions,
)


def _school(slug="demo-school", name="Demo School", pk=42):
    return SimpleNamespace(slug=slug, name=name, pk=pk, id=pk)


def _request(*, mode="experience", school=None, user=None, params=None):
    """Minimal request stub that satisfies the rail service."""
    if user is None:
        user = SimpleNamespace(
            is_authenticated=True,
            is_staff=True,
            is_superuser=True,
            role="ADMIN",
            pk=1,
            id=1,
        )
    return SimpleNamespace(
        school=school,
        user=user,
        GET=(params or {}),
        path=f"/studio/{mode}/",
    )


def _stub_posture(mode="live_cloud"):
    """Patch probe_ai_provider_reachable to return a posture dict."""
    return {
        "reachable": mode in ("live_cloud", "live_local"),
        "provider": {
            "live_cloud": "litellm",
            "live_local": "ollama",
            "guided": "rules",
            "unavailable": "none",
        }.get(mode, "none"),
        "posture_mode": mode,
        "rules_fallback_enabled": mode == "guided",
        "fallback_active": mode == "guided",
        "deployment_profile": "online",
        "litellm_configured": True,
        "ollama_configured": False,
    }


# ---------------------------------------------------------------------------
# build_context_snapshot
# ---------------------------------------------------------------------------


class BuildContextSnapshotTests(SimpleTestCase):
    def test_returns_correct_mode_and_hashed_school(self):
        request = _request(mode="experience", school=_school(slug="acme"))
        with patch(
            "apps.portal.ai_provider.probe_ai_provider_reachable",
            return_value=_stub_posture("live_cloud"),
            create=True,
        ):
            snap = build_context_snapshot(request, mode="experience")
        self.assertIsInstance(snap, CopilotContextSnapshot)
        self.assertEqual(snap.mode, "experience")
        self.assertEqual(snap.surface_name, "experience")
        self.assertEqual(snap.posture_mode, "live_cloud")
        # Hash is sha256[:8] hex — never the raw slug.
        self.assertEqual(len(snap.school_slug_hash), 8)
        self.assertNotEqual(snap.school_slug_hash, "acme")
        self.assertNotIn("acme", snap.school_slug_hash)

    def test_unknown_mode_maps_to_shell_surface(self):
        request = _request(mode="weirdmode", school=_school())
        with patch(
            "apps.portal.ai_provider.probe_ai_provider_reachable",
            return_value=_stub_posture("guided"),
            create=True,
        ):
            snap = build_context_snapshot(request, mode="weirdmode")
        self.assertEqual(snap.surface_name, "shell")
        self.assertEqual(snap.posture_mode, "guided")

    def test_no_school_yields_none_hash(self):
        request = _request(mode="control", school=None)
        with patch(
            "apps.portal.ai_provider.probe_ai_provider_reachable",
            return_value=_stub_posture("unavailable"),
            create=True,
        ):
            snap = build_context_snapshot(request, mode="control")
        self.assertEqual(snap.school_slug_hash, "none")
        self.assertEqual(snap.posture_mode, "unavailable")

    def test_selection_summary_extracted_from_query(self):
        request = _request(mode="experience", school=_school(), params={"tour": "step-3"})
        with patch(
            "apps.portal.ai_provider.probe_ai_provider_reachable",
            return_value=_stub_posture("live_cloud"),
            create=True,
        ):
            # Wrap params in a stub with .get()
            request.GET = SimpleNamespace(get=lambda k, d=None: {"tour": "step-3"}.get(k, d))
            snap = build_context_snapshot(request, mode="experience")
        self.assertEqual(snap.selection_summary, "step-3")


# ---------------------------------------------------------------------------
# generate_insights — cloud vs rules
# ---------------------------------------------------------------------------


class GenerateInsightsTests(SimpleTestCase):
    def _snap(self, surface="experience", posture="live_cloud"):
        return CopilotContextSnapshot(
            mode=surface,
            school_slug_hash="abc12345",
            surface_name=surface,
            selection_summary=None,
            posture_mode=posture,
        )

    def test_cloud_path_returns_source_cloud(self):
        snap = self._snap(posture="live_cloud")
        request = _request(mode="experience", school=_school())
        fake_response = (
            '{"insights": [{"id": "x1", "title": "Try this", "body": "Use the palette tool to generate WCAG-safe colors fast."},'
            '{"id": "x2", "title": "Compare themes", "body": "Side-by-side view shows token-level deltas before publish."},'
            '{"id": "x3", "title": "Preview by role", "body": "Open admin/teacher previews to verify branding lands."}]}',
            {"provider": "litellm"},
        )
        with patch(
            "apps.studio_os.copilot_rail_service.invoke_with_request",
            return_value=fake_response,
        ):
            insights = generate_insights(snap, request=request, n=3)
        self.assertEqual(len(insights), 3)
        for i in insights:
            self.assertIsInstance(i, CopilotInsight)
            self.assertEqual(i.source, "cloud")

    def test_rules_fallback_when_ai_unreachable(self):
        """invoke_with_request returns None -> rules layer activates."""
        snap = self._snap(posture="guided")
        request = _request(school=_school())
        with patch(
            "apps.studio_os.copilot_rail_service.invoke_with_request",
            return_value=None,
        ):
            insights = generate_insights(snap, request=request, n=3)
        self.assertEqual(len(insights), 3)
        for i in insights:
            self.assertEqual(i.source, "rules")

    def test_returns_exactly_n_insights(self):
        snap = self._snap(posture="guided")
        request = _request(school=_school())
        with patch(
            "apps.studio_os.copilot_rail_service.invoke_with_request",
            return_value=None,
        ):
            for n in (1, 2, 3):
                with self.subTest(n=n):
                    insights = generate_insights(snap, request=request, n=n)
                    self.assertEqual(len(insights), n)

    def test_unavailable_posture_short_circuits_to_rules(self):
        """When posture is 'unavailable' we never call the gateway."""
        snap = self._snap(posture="unavailable")
        request = _request(school=_school())
        with patch(
            "apps.studio_os.copilot_rail_service.invoke_with_request",
            return_value=None,
        ) as mock_invoke:
            insights = generate_insights(snap, request=request, n=3)
        mock_invoke.assert_not_called()
        self.assertEqual(len(insights), 3)
        for i in insights:
            self.assertEqual(i.source, "rules")

    def test_unparseable_cloud_response_falls_back_to_rules(self):
        snap = self._snap(posture="live_cloud")
        request = _request(school=_school())
        with patch(
            "apps.studio_os.copilot_rail_service.invoke_with_request",
            return_value=("this is not json at all", {}),
        ):
            insights = generate_insights(snap, request=request, n=3)
        for i in insights:
            self.assertEqual(i.source, "rules")

    def test_cross_tenant_leak_in_cloud_response_falls_back(self):
        """Cloud response that mentions a foreign tenant slug must be rejected."""
        snap = self._snap(posture="live_cloud")
        request = _request(school=_school(slug="acme"))
        leak_payload = (
            '{"insights": [{"id": "1", "title": "Foreign", "body": "Open school-other-tenant settings now."},'
            '{"id": "2", "title": "Foreign", "body": "Visit school-other-tenant theme."},'
            '{"id": "3", "title": "Foreign", "body": "Switch to school-other-tenant."}]}',
            {},
        )
        with patch(
            "apps.studio_os.copilot_rail_service.invoke_with_request",
            return_value=leak_payload,
        ):
            insights = generate_insights(snap, request=request, n=3)
        for i in insights:
            self.assertEqual(i.source, "rules")
            self.assertNotIn("other-tenant", i.body)


# ---------------------------------------------------------------------------
# resolve_quick_actions
# ---------------------------------------------------------------------------


class ResolveQuickActionsTests(SimpleTestCase):
    def test_anonymous_request_returns_empty(self):
        snap = CopilotContextSnapshot(
            mode="experience",
            school_slug_hash="aaaa1111",
            surface_name="experience",
            selection_summary=None,
            posture_mode="guided",
        )
        anon_request = _request(
            user=SimpleNamespace(is_authenticated=False, is_staff=False, role="", pk=None, id=None),
            school=_school(),
        )
        actions = resolve_quick_actions(snap, request=anon_request)
        self.assertEqual(actions, [])

    def test_capped_at_max_quick_actions(self):
        snap = CopilotContextSnapshot(
            mode="shell",
            school_slug_hash="aaaa1111",
            surface_name="shell",
            selection_summary=None,
            posture_mode="live_cloud",
        )
        staff_request = _request(school=_school())
        actions = resolve_quick_actions(snap, request=staff_request)
        # Staff sees many actions; rail caps at 6.
        self.assertLessEqual(len(actions), MAX_QUICK_ACTIONS)

    def test_experience_surface_prefers_experience_urls(self):
        snap = CopilotContextSnapshot(
            mode="experience",
            school_slug_hash="aaaa1111",
            surface_name="experience",
            selection_summary=None,
            posture_mode="live_cloud",
        )
        staff_request = _request(school=_school())
        actions = resolve_quick_actions(snap, request=staff_request)
        if actions:
            # The top-ranked action should be experience-related (URL contains
            # 'experience' OR has kind palette/install which experience favors).
            top = actions[0]
            url = top.get("url", "")
            kind = top.get("kind", "")
            self.assertTrue(
                "experience" in url.lower()
                or kind in {"palette", "install", "settings", "deploy"},
                f"Top action not surface-aligned: {top}",
            )

    def test_tenant_user_role_filtered(self):
        """Non-staff role gets fewer actions than staff."""
        snap = CopilotContextSnapshot(
            mode="shell",
            school_slug_hash="aaaa1111",
            surface_name="shell",
            selection_summary=None,
            posture_mode="guided",
        )
        teacher_request = _request(
            user=SimpleNamespace(
                is_authenticated=True,
                is_staff=False,
                is_superuser=False,
                role="TEACHER",
                pk=2,
                id=2,
            ),
            school=_school(),
        )
        staff_request = _request(school=_school())
        teacher_actions = resolve_quick_actions(snap, request=teacher_request)
        staff_actions = resolve_quick_actions(snap, request=staff_request)
        self.assertLessEqual(len(teacher_actions), len(staff_actions))


# ---------------------------------------------------------------------------
# Cross-tenant safety + logger hygiene
# ---------------------------------------------------------------------------


class TenantIsolationTests(SimpleTestCase):
    def test_snapshot_school_a_does_not_leak_school_b(self):
        """The hashed slug from one tenant must differ from another."""
        request_a = _request(school=_school(slug="alpha"))
        request_b = _request(school=_school(slug="bravo"))
        with patch(
            "apps.portal.ai_provider.probe_ai_provider_reachable",
            return_value=_stub_posture("live_cloud"),
            create=True,
        ):
            snap_a = build_context_snapshot(request_a, mode="experience")
            snap_b = build_context_snapshot(request_b, mode="experience")
        self.assertNotEqual(snap_a.school_slug_hash, snap_b.school_slug_hash)
        # Both hashes are 8-hex.
        self.assertEqual(len(snap_a.school_slug_hash), 8)
        self.assertEqual(len(snap_b.school_slug_hash), 8)
        # Slugs never appear in the hash.
        self.assertNotIn("alpha", snap_a.school_slug_hash)
        self.assertNotIn("bravo", snap_b.school_slug_hash)


class LoggerHygieneTests(SimpleTestCase):
    def test_logger_does_not_emit_raw_slug(self):
        """Force a fallback path and confirm the slug never lands in logs."""
        snap = CopilotContextSnapshot(
            mode="experience",
            school_slug_hash="cccc3333",
            surface_name="experience",
            selection_summary=None,
            posture_mode="live_cloud",
        )
        request = _request(school=_school(slug="secretslug"))
        # Force unparseable response so the WARN/INFO branch fires.
        with patch(
            "apps.studio_os.copilot_rail_service.invoke_with_request",
            return_value=("totally not json", {}),
        ):
            with self.assertLogs(
                "apps.studio_os.copilot_rail_service",
                level=logging.DEBUG,
            ) as cm:
                # Trigger the info-log branch by making cloud unparseable.
                generate_insights(snap, request=request, n=3)
                # Also exercise the warn branch via cross-tenant injection.
                with patch(
                    "apps.studio_os.copilot_rail_service.invoke_with_request",
                    return_value=(
                        '{"insights": [{"id":"1","title":"foreign","body":"open school-other settings"},'
                        '{"id":"2","title":"x","body":"x"},'
                        '{"id":"3","title":"y","body":"y"}]}',
                        {},
                    ),
                ):
                    generate_insights(snap, request=request, n=3)
        full_log = "\n".join(cm.output)
        # Slug must never appear raw; only the hashed prefix is allowed.
        self.assertNotIn("secretslug", full_log)


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


class BuildRailPayloadTests(SimpleTestCase):
    def test_payload_has_three_top_level_keys(self):
        request = _request(school=_school())
        with patch(
            "apps.portal.ai_provider.probe_ai_provider_reachable",
            return_value=_stub_posture("guided"),
            create=True,
        ), patch(
            "apps.studio_os.copilot_rail_service.invoke_with_request",
            return_value=None,
        ):
            payload = build_rail_payload(request, mode="experience", n=3)
        self.assertIn("snapshot", payload)
        self.assertIn("insights", payload)
        self.assertIn("quick_actions", payload)
        self.assertEqual(len(payload["insights"]), 3)
        for ins in payload["insights"]:
            self.assertEqual(ins["source"], "rules")
