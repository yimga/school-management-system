"""Tests for Live Banner Studio program (sources, announcements, composition)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone

from apps.siteconfig.cockpit_activity_ticker_realdata import (
    LIVE_BANNER_SOURCE_REGISTRY,
    resolve_manager_ticker_cards,
)
from apps.siteconfig.cockpit_live_banner_program import (
    announcements_to_cards,
    compose_live_banner_cards,
    default_sources_enabled,
    draft_emergency_announcement,
    finalize_live_banner_section,
    resolve_active_announcements,
    resolve_sources_enabled,
    suggest_live_banner_program,
    validate_live_banner_program_payload,
)
from apps.siteconfig.forms_cockpit import (
    _parse_live_banner_announcements,
    _serialize_live_banner_announcements,
)


class LiveBannerRegistryTests(SimpleTestCase):
    def test_registry_covers_manager_and_tenant_hosts(self):
        hosts = {entry["host"] for entry in LIVE_BANNER_SOURCE_REGISTRY}
        self.assertIn("manager", hosts)
        self.assertIn("tenant", hosts)

    def test_default_sources_match_registry_defaults(self):
        self.assertGreater(len(default_sources_enabled("manager")), 0)
        self.assertGreater(len(default_sources_enabled("tenant")), 0)


class LiveBannerSourceFilterTests(SimpleTestCase):
    def test_empty_list_disables_all_sources(self):
        enabled = resolve_sources_enabled([], "manager")
        self.assertEqual(enabled, frozenset())

    def test_unknown_ids_are_ignored(self):
        enabled = resolve_sources_enabled(["provisioning", "not-real"], "manager")
        self.assertEqual(enabled, frozenset({"provisioning"}))

    @patch(
        "apps.siteconfig.cockpit_activity_ticker_realdata._source_school_provisioning",
        return_value=[{"text": "1 school", "severity": "success"}],
    )
    @patch(
        "apps.siteconfig.cockpit_activity_ticker_realdata._source_migration_audit_events",
        return_value=[{"text": "audit", "severity": "info"}],
    )
    def test_manager_resolver_honors_enabled_sources(self, _audit, _provision):
        all_cards = resolve_manager_ticker_cards(default_sources_enabled("manager"))
        filtered = resolve_manager_ticker_cards(frozenset({"provisioning"}))
        self.assertGreaterEqual(len(all_cards), len(filtered))
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["text"], "1 school")


class LiveBannerAnnouncementTests(SimpleTestCase):
    def test_parse_and_serialize_round_trip(self):
        raw = "Campus closed | emergency | danger | yes | | | all"
        parsed = _parse_live_banner_announcements(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["kind"], "emergency")
        self.assertTrue(parsed[0]["pin"])
        serialized = _serialize_live_banner_announcements(parsed)
        self.assertIn("Campus closed", serialized)

    def test_pinned_emergency_sorts_first(self):
        now = timezone.now()
        announcements = resolve_active_announcements(
            [
                {"text": "Later info", "kind": "info", "pin": False},
                {
                    "text": "Emergency now",
                    "kind": "emergency",
                    "pin": True,
                    "starts_at": (now - timedelta(minutes=1)).isoformat(),
                },
            ],
            RequestFactory().get("/"),
        )
        self.assertEqual(announcements[0]["text"], "Emergency now")

    def test_compose_puts_announcements_before_cards(self):
        section = {
            "cards": [{"text": "Metric card", "severity": "info"}],
            "announcements": [
                {"text": "Pinned alert", "kind": "alert", "pin": True, "audiences": ["all"]}
            ],
        }
        merged = compose_live_banner_cards(section, RequestFactory().get("/"))
        self.assertEqual(merged[0]["text"], "Pinned alert")
        self.assertEqual(merged[1]["text"], "Metric card")

    def test_emergency_cards_get_assertive_aria(self):
        cards = announcements_to_cards(
            [{"text": "Evacuate", "kind": "emergency", "pin": True}]
        )
        self.assertEqual(cards[0]["aria_live"], "assertive")


class LiveBannerAudienceTests(SimpleTestCase):
    def test_parent_audience_filters_non_parent_roles(self):
        request = RequestFactory().get("/portal/parent/")
        request.user = type("UserStub", (), {"role": "TEACHER"})()
        active = resolve_active_announcements(
            [
                {
                    "text": "Parent pickup",
                    "kind": "info",
                    "audiences": ["parent"],
                }
            ],
            request,
        )
        self.assertEqual(active, [])


class LiveBannerSuggestTests(SimpleTestCase):
    def test_suggest_program_validates(self):
        program = suggest_live_banner_program(RequestFactory().get("/super/"))
        self.assertEqual(validate_live_banner_program_payload(program), [])

    def test_draft_emergency_has_required_fields(self):
        draft = draft_emergency_announcement(RequestFactory().get("/"))
        self.assertEqual(draft["kind"], "emergency")
        self.assertTrue(draft["pin"])


class LiveBannerFinalizeTests(SimpleTestCase):
    def test_finalize_section_rewrites_cards(self):
        section = {
            "cards": [{"text": "Manual", "severity": "info"}],
            "announcements": [{"text": "Alert", "kind": "alert", "audiences": ["all"]}],
        }
        finalized = finalize_live_banner_section(section, RequestFactory().get("/"))
        self.assertEqual(finalized["cards"][0]["text"], "Alert")
