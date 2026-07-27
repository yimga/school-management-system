"""Calendar event sync pushes school events to connected calendars, idempotently.

Consumes the tenant's google_calendar / outlook_calendar OAuth token to
create-or-update events, storing the external id + a content hash in
``SchoolEvent.metadata["calendar_sync"]`` so re-runs PATCH (or skip) instead of
duplicating. All HTTP goes through the patched ``_http_json`` seam.
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.integrations_marketplace import calendar_sync
from apps.integrations_marketplace.calendar_sync import (
    push_event_to_calendars,
    sync_school_events,
)
from apps.school_events.models import SchoolEvent
from apps.schools.models import School


def _google_only(school, slug):
    return "tok-google" if slug == "google_calendar" else ""


class CalendarSyncServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Cal School", slug="cal-school", subdomain="cal-school", is_active=True
        )

    def _event(self, **kw):
        defaults = dict(
            school=self.school,
            title="Sports Day",
            status=SchoolEvent.Status.PUBLISHED,
            start_at=timezone.now() + timedelta(days=7),
        )
        defaults.update(kw)
        return SchoolEvent.objects.create(**defaults)

    def test_not_connected_provider_is_skipped_and_no_metadata_written(self):
        event = self._event()
        with mock.patch(
            "apps.integrations_marketplace.token_access.get_valid_access_token",
            return_value="",
        ):
            result = push_event_to_calendars(event)
        self.assertTrue(result["ok"])
        self.assertEqual(
            result["providers"]["google_calendar"]["status"], "not_connected"
        )
        event.refresh_from_db()
        self.assertNotIn("calendar_sync", event.metadata or {})

    def test_create_then_second_run_is_unchanged_no_duplicate(self):
        event = self._event()
        calls = []

        def fake_http(method, url, token, body):
            calls.append((method, url))
            return (200 if method == "PATCH" else 201), {"id": "gcal-1"}

        with mock.patch(
            "apps.integrations_marketplace.token_access.get_valid_access_token",
            side_effect=_google_only,
        ), mock.patch(
            "apps.integrations_marketplace.calendar_sync._http_json",
            side_effect=fake_http,
        ):
            r1 = push_event_to_calendars(event)
            self.assertEqual(r1["providers"]["google_calendar"]["status"], "created")
            self.assertEqual(
                r1["providers"]["google_calendar"]["external_id"], "gcal-1"
            )
            event.refresh_from_db()
            self.assertEqual(
                event.metadata["calendar_sync"]["google_calendar"]["external_id"],
                "gcal-1",
            )
            # Second run with no change → unchanged, and NO second HTTP call.
            calls.clear()
            r2 = push_event_to_calendars(event)
            self.assertEqual(r2["providers"]["google_calendar"]["status"], "unchanged")
            self.assertEqual(calls, [])

    def test_change_triggers_patch_to_existing_external_id(self):
        event = self._event()

        def fake_http(method, url, token, body):
            return (200 if method == "PATCH" else 201), {"id": "gcal-1"}

        with mock.patch(
            "apps.integrations_marketplace.token_access.get_valid_access_token",
            side_effect=_google_only,
        ), mock.patch(
            "apps.integrations_marketplace.calendar_sync._http_json",
            side_effect=fake_http,
        ):
            push_event_to_calendars(event)  # initial create

        event.title = "Sports Day (rescheduled)"
        event.save(update_fields=["title", "updated_at"])

        calls = []

        def fake_http2(method, url, token, body):
            calls.append((method, url))
            return 200, {"id": "gcal-1"}

        with mock.patch(
            "apps.integrations_marketplace.token_access.get_valid_access_token",
            side_effect=_google_only,
        ), mock.patch(
            "apps.integrations_marketplace.calendar_sync._http_json",
            side_effect=fake_http2,
        ):
            r = push_event_to_calendars(event)

        self.assertEqual(r["providers"]["google_calendar"]["status"], "updated")
        self.assertTrue(calls)
        self.assertEqual(calls[0][0], "PATCH")
        self.assertIn("gcal-1", calls[0][1])

    def test_sweep_pushes_only_future_published_events(self):
        self._event(title="Future Published")  # eligible
        self._event(
            title="Past Published", start_at=timezone.now() - timedelta(days=3)
        )  # past → excluded
        self._event(title="Future Draft", status=SchoolEvent.Status.DRAFT)  # draft → excluded

        def fake_http(method, url, token, body):
            return 201, {"id": "gcal-x"}

        with mock.patch(
            "apps.integrations_marketplace.token_access.get_valid_access_token",
            side_effect=_google_only,
        ), mock.patch(
            "apps.integrations_marketplace.calendar_sync._http_json",
            side_effect=fake_http,
        ):
            summary = sync_school_events(self.school)

        self.assertEqual(summary["pushed"], 1)
        self.assertEqual(summary["errors"], 0)

    def test_api_error_records_error_and_leaves_no_external_id(self):
        event = self._event()

        def fake_http(method, url, token, body):
            return 500, {}

        with mock.patch(
            "apps.integrations_marketplace.token_access.get_valid_access_token",
            side_effect=_google_only,
        ), mock.patch(
            "apps.integrations_marketplace.calendar_sync._http_json",
            side_effect=fake_http,
        ):
            result = push_event_to_calendars(event)

        self.assertEqual(result["providers"]["google_calendar"]["status"], "error")
        event.refresh_from_db()
        self.assertNotIn("calendar_sync", event.metadata or {})


class CalendarSyncTaskRegistrationTests(SimpleTestCase):
    def test_beat_task_registers_with_expected_name(self):
        # Must match the beat entry's "task" string exactly, or the beat-registry
        # gate goes red (a beat entry pointing at an unregistered task).
        task = calendar_sync.sync_calendar_events
        if task is None:
            # Celery not installed in this env — the sweep must still be callable.
            self.assertTrue(callable(calendar_sync._sync_calendar_events_all_tenants))
            return
        self.assertEqual(
            getattr(task, "name", None),
            "integrations_marketplace.sync_calendar_events",
        )


class CalendarSyncFanOutTests(TestCase):
    def test_all_tenants_sweep_iterates_active_schools_only(self):
        School.objects.create(name="A", slug="a", subdomain="a", is_active=True)
        School.objects.create(name="B", slug="b", subdomain="b", is_active=True)
        School.objects.create(name="C", slug="c", subdomain="c", is_active=False)

        with mock.patch.object(
            calendar_sync,
            "sync_school_events",
            return_value={"pushed": 1, "skipped": 0, "errors": 0},
        ):
            totals = calendar_sync._sync_calendar_events_all_tenants()

        self.assertEqual(totals["schools_processed"], 2)  # inactive C skipped
        self.assertEqual(totals["pushed"], 2)
