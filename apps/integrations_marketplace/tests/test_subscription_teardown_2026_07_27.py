"""Disconnecting a connector stops its upstream push subscription.

connector_connected auto-subscribes; without this the disconnect leaves the
upstream channel alive (Google hammers a dead webhook, the Graph subscription
lingers, the renewer rotates a ghost). The connector_disconnected receiver
stops the channel, clears config["push_subscription"], and scrubs stored OAuth
secrets. All outbound HTTP goes through the patched _http_json seam.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from apps.integrations_marketplace import subscription_teardown
from apps.integrations_marketplace.connector_registry import get_connector
from apps.integrations_marketplace.oauth import persist_oauth_tokens
from apps.integrations_marketplace.signals import connector_disconnected
from apps.integrations_marketplace.subscription_teardown import teardown_for_row
from apps.schools.models import School


def _connected_row(school, slug, sub, scope):
    row = persist_oauth_tokens(
        connector=get_connector(slug),
        school=school,
        campus=None,
        token_response={
            "access_token": "tok",
            "refresh_token": "ref",
            "scope": scope,
            "expires_in": 3600,
        },
    )
    config = dict(row.config or {})
    config["push_subscription"] = sub
    row.config = config
    row.save(update_fields=["config", "updated_at"])
    return row


class SubscriptionTeardownTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="TD School", slug="td-school", subdomain="td-school", is_active=True
        )

    def test_google_teardown_stops_channel_and_scrubs(self):
        row = _connected_row(
            self.school,
            "google_calendar",
            {
                "provider": "google_calendar",
                "channel_id": "chan-1",
                "resource_id": "res-1",
                "calendar_id": "primary",
            },
            "https://www.googleapis.com/auth/calendar.events",
        )
        calls = []

        def fake_http(method, url, token, body):
            calls.append((method, url, body))
            return 204, {}

        with mock.patch.object(subscription_teardown, "_http_json", side_effect=fake_http):
            result = teardown_for_row(row)

        self.assertEqual(result["status"], "stopped")
        # Hit Google channels/stop with the channel + resource id.
        self.assertTrue(calls)
        method, url, body = calls[0]
        self.assertEqual(method, "POST")
        self.assertIn("channels/stop", url)
        self.assertEqual(body, {"id": "chan-1", "resourceId": "res-1"})
        # Local state cleared + secrets scrubbed.
        row.refresh_from_db()
        self.assertNotIn("push_subscription", row.config)
        self.assertNotIn("access_token", row.config)
        self.assertNotIn("refresh_token", row.config)

    def test_graph_teardown_deletes_subscription(self):
        row = _connected_row(
            self.school,
            "outlook_calendar",
            {
                "provider": "outlook_calendar",
                "subscription_id": "sub-9",
                "resource": "/me/events",
            },
            "offline_access Calendars.ReadWrite User.Read",
        )
        calls = []

        def fake_http(method, url, token, body):
            calls.append((method, url))
            return 204, {}

        with mock.patch.object(subscription_teardown, "_http_json", side_effect=fake_http):
            result = teardown_for_row(row)

        self.assertEqual(result["status"], "stopped")
        method, url = calls[0]
        self.assertEqual(method, "DELETE")
        self.assertIn("/subscriptions/sub-9", url)
        row.refresh_from_db()
        self.assertNotIn("push_subscription", row.config)

    def test_graph_404_is_idempotent_success(self):
        row = _connected_row(
            self.school,
            "outlook_calendar",
            {"provider": "outlook_calendar", "subscription_id": "gone"},
            "offline_access Calendars.ReadWrite User.Read",
        )
        with mock.patch.object(
            subscription_teardown, "_http_json", return_value=(404, {})
        ):
            result = teardown_for_row(row)
        self.assertEqual(result["status"], "stopped")

    def test_upstream_failure_still_clears_local_state(self):
        row = _connected_row(
            self.school,
            "google_calendar",
            {"provider": "google_calendar", "channel_id": "c", "resource_id": "r"},
            "https://www.googleapis.com/auth/calendar.events",
        )
        with mock.patch.object(
            subscription_teardown, "_http_json", return_value=(500, {})
        ):
            result = teardown_for_row(row)
        self.assertEqual(result["status"], "stop_failed")
        row.refresh_from_db()
        # Even though upstream stop failed, we must not leave stale state.
        self.assertNotIn("push_subscription", row.config)
        self.assertNotIn("access_token", row.config)

    def test_no_subscription_still_scrubs_secrets(self):
        row = persist_oauth_tokens(
            connector=get_connector("google_calendar"),
            school=self.school,
            campus=None,
            token_response={
                "access_token": "tok",
                "refresh_token": "ref",
                "scope": "https://www.googleapis.com/auth/calendar.events",
                "expires_in": 3600,
            },
        )
        called = []
        with mock.patch.object(
            subscription_teardown,
            "_http_json",
            side_effect=lambda *a, **k: called.append(a) or (204, {}),
        ):
            result = teardown_for_row(row)
        self.assertEqual(result["status"], "no_subscription")
        self.assertEqual(called, [])  # no upstream call when nothing to stop
        row.refresh_from_db()
        self.assertNotIn("access_token", row.config)

    def test_receiver_fires_on_connector_disconnected_signal(self):
        row = _connected_row(
            self.school,
            "google_calendar",
            {"provider": "google_calendar", "channel_id": "c1", "resource_id": "r1"},
            "https://www.googleapis.com/auth/calendar.events",
        )
        with mock.patch.object(
            subscription_teardown, "_http_json", return_value=(204, {})
        ):
            connector_disconnected.send(
                sender="integrations_marketplace.connector",
                row=row,
                connector="google_calendar",
                school=self.school,
                campus=None,
                action="disconnected",
            )
        row.refresh_from_db()
        self.assertNotIn("push_subscription", row.config)
