"""Integration consumers actually USE the tokens tenants connect.

The audit found connected OAuth tokens were stored but never consumed. These
tests lock the seams that changed that:

* ``get_valid_access_token`` resolves + decrypts a tenant's stored token.
* ``VideoConferenceService`` threads ``school`` so a Zoom meeting is created
  with the tenant's connected token (not the legacy fallback).
* Teams meetings are created via Graph when connected, and fall back to a REAL
  Jitsi room when not — never a ``ValueError`` (the old dispatch raised for
  TEAMS) and never a fabricated ``teams.microsoft.com`` link.
"""

from __future__ import annotations

import time
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.communication.video_conferencing import (
    VideoConferenceProvider,
    VideoConferenceService,
)


def _host():
    return SimpleNamespace(email="teacher@example.com", id=1, username="teacher")


class TeamsMeetingConsumerTests(SimpleTestCase):
    def test_teams_without_connection_falls_back_to_real_jitsi(self):
        svc = VideoConferenceService(VideoConferenceProvider.TEAMS)  # no school
        result = svc.create_meeting(_host(), "Parent Conf", datetime(2026, 1, 1, 10, 0), 30)
        self.assertTrue(result.get("join_url"))
        # Not a fabricated Teams link.
        self.assertNotIn("teams.microsoft.com", result["join_url"])
        self.assertEqual(result.get("provider"), "jitsi")
        self.assertEqual(result.get("requested_provider"), "teams")
        self.assertEqual(
            result.get("provider_fallback_reason"), "microsoft_teams_not_connected"
        )

    def test_teams_dispatch_no_longer_raises(self):
        # The dispatch used to `raise ValueError` for TEAMS.
        svc = VideoConferenceService(VideoConferenceProvider.TEAMS)
        result = svc.create_meeting(_host(), "x", datetime(2026, 1, 1, 10, 0), 30)
        self.assertIsInstance(result, dict)

    def test_teams_with_connection_creates_via_graph(self):
        svc = VideoConferenceService(
            VideoConferenceProvider.TEAMS, school=SimpleNamespace(pk=1)
        )
        fake_resp = SimpleNamespace(
            status_code=201,
            json=lambda: {
                "id": "AAA",
                "joinWebUrl": "https://teams.microsoft.com/l/meetup-join/xyz",
            },
            text="",
        )
        with mock.patch(
            "apps.integrations_marketplace.token_access.get_valid_access_token",
            return_value="tenant-teams-token",
        ), mock.patch("requests.post", return_value=fake_resp) as post:
            result = svc.create_meeting(_host(), "Conf", datetime(2026, 1, 1, 10, 0), 30)

        self.assertEqual(result.get("provider"), "teams")
        self.assertEqual(
            result.get("join_url"), "https://teams.microsoft.com/l/meetup-join/xyz"
        )
        # It hit Graph onlineMeetings with the tenant bearer.
        self.assertIn("onlineMeetings", post.call_args[0][0])
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer tenant-teams-token",
        )

    def test_teams_graph_failure_falls_back_to_jitsi(self):
        svc = VideoConferenceService(
            VideoConferenceProvider.TEAMS, school=SimpleNamespace(pk=1)
        )
        fake_resp = SimpleNamespace(status_code=403, json=lambda: {}, text="forbidden")
        with mock.patch(
            "apps.integrations_marketplace.token_access.get_valid_access_token",
            return_value="tenant-teams-token",
        ), mock.patch("requests.post", return_value=fake_resp):
            result = svc.create_meeting(_host(), "Conf", datetime(2026, 1, 1, 10, 0), 30)
        self.assertEqual(result.get("provider"), "jitsi")
        self.assertEqual(result.get("provider_fallback_reason"), "teams_api_error")


class ZoomThreadsSchoolTests(SimpleTestCase):
    def test_zoom_meeting_passes_school_to_integration(self):
        school = SimpleNamespace(pk=7)
        svc = VideoConferenceService(VideoConferenceProvider.ZOOM, school=school)
        with mock.patch(
            "apps.communication.integrations.ZoomIntegration"
        ) as zoom_cls:
            zoom_cls.return_value.create_meeting.return_value = {
                "success": True,
                "meeting_id": "123",
                "join_url": "https://zoom.us/j/123",
            }
            result = svc.create_meeting(
                SimpleNamespace(email="t@x.com"), "C", datetime(2026, 1, 1, 10, 0), 30
            )
        # The tenant is threaded so the connected Zoom token is used.
        zoom_cls.assert_called_once_with(school=school)
        self.assertEqual(result["join_url"], "https://zoom.us/j/123")


class GetValidAccessTokenTests(TestCase):
    def test_returns_decrypted_token_for_connected_school(self):
        from apps.integrations_marketplace.connector_registry import get_connector
        from apps.integrations_marketplace.oauth import persist_oauth_tokens
        from apps.integrations_marketplace.token_access import get_valid_access_token
        from apps.schools.models import School

        school = School.objects.create(
            name="Zoomy", slug="zoomy", subdomain="zoomy", is_active=True
        )
        persist_oauth_tokens(
            connector=get_connector("zoom"),
            school=school,
            campus=None,
            token_response={
                "access_token": "tok-1",
                "refresh_token": "ref-1",
                "scope": "meeting:write meeting:read",
                # Far-future so the freshness check does not attempt a refresh.
                "expires_at": int(time.time()) + 3600,
            },
        )
        self.assertEqual(get_valid_access_token(school, "zoom"), "tok-1")

    def test_returns_empty_when_not_connected(self):
        from apps.integrations_marketplace.token_access import get_valid_access_token
        from apps.schools.models import School

        school = School.objects.create(
            name="Bare", slug="bare", subdomain="bare", is_active=True
        )
        self.assertEqual(get_valid_access_token(school, "zoom"), "")

    def test_none_school_returns_empty(self):
        from apps.integrations_marketplace.token_access import get_valid_access_token

        self.assertEqual(get_valid_access_token(None, "zoom"), "")
