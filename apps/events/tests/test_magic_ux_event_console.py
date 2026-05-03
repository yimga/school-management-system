"""Magic UX event console empty states + instrumentation."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class EventConsoleMagicUxTests(TestCase):
    databases = {"default"}

    def test_empty_rows_render_action_states_with_hooks(self):
        req = RequestFactory().get("/events/")
        req.user = AnonymousUser()
        html = render_to_string(
            "events/event_console.html",
            {
                "LANGUAGE_CODE": getattr(settings, "LANGUAGE_CODE", "en"),
                "page_title": "Events",
                "page_subtitle": "Sub",
                "domain_rows": [],
                "platform_rows": [],
                "action_url": "/backend/",
            },
            request=req,
        )
        self.assertIn('data-rmc-event-console="1"', html)
        self.assertIn('data-task="event_console"', html)
        self.assertGreaterEqual(html.count("dashboard-empty-state"), 2)
