"""Pillar 3 — Verified Communications: institutional stamp tag tests."""

from __future__ import annotations

from types import SimpleNamespace

from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase


def _render(notification, request) -> str:
    """Render the stamp tag against an explicit request + notification."""
    template = Template(
        "{% load institutional_stamp %}{% institutional_stamp notif %}"
    )
    ctx = Context({"notif": notification, "request": request})
    return template.render(ctx).strip()


class InstitutionalStampTagTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_stamp_renders_for_matching_tenant(self):
        request = self.factory.get("/")
        request.school = SimpleNamespace(id=42, name="Riverdale Academy")
        notification = SimpleNamespace(school_id=42, title="Term begins")

        out = _render(notification, request)

        self.assertIn("rmc-institutional-stamp", out)
        self.assertIn("Riverdale Academy", out)
        # The SVG checkmark must be present (proves the partial rendered).
        self.assertIn("<svg", out)
        # CSP enforce mode is on — partial must not emit inline `style="..."`.
        self.assertNotIn('style="', out)

    def test_stamp_empty_for_mismatched_tenant(self):
        request = self.factory.get("/")
        request.school = SimpleNamespace(id=1, name="Tenant A")
        notification = SimpleNamespace(school_id=999, title="Cross-tenant push")

        out = _render(notification, request)

        self.assertEqual(out, "")

    def test_stamp_empty_when_no_school_context(self):
        # Login page / marketing surface — no request.school at all.
        request = self.factory.get("/")
        # Deliberately no request.school assignment; getattr returns None.
        notification = SimpleNamespace(school_id=42)

        out = _render(notification, request)

        self.assertEqual(out, "")

    def test_stamp_empty_when_request_school_is_none(self):
        request = self.factory.get("/")
        request.school = None
        notification = SimpleNamespace(school_id=42)

        out = _render(notification, request)
        self.assertEqual(out, "")

    def test_stamp_empty_when_notification_lacks_school(self):
        # apps.finance.models.Notification has no school FK today —
        # the tag must degrade silently rather than throw.
        request = self.factory.get("/")
        request.school = SimpleNamespace(id=42, name="Riverdale Academy")
        notification = SimpleNamespace(title="Legacy row, no school FK")

        out = _render(notification, request)
        self.assertEqual(out, "")

    def test_stamp_handles_none_notification_gracefully(self):
        request = self.factory.get("/")
        request.school = SimpleNamespace(id=42, name="Riverdale Academy")

        out = _render(None, request)
        self.assertEqual(out, "")

    def test_stamp_id_compared_as_string_for_uuid_safety(self):
        # FK could be int / str / UUID — compare as str so the match works.
        request = self.factory.get("/")
        request.school = SimpleNamespace(id="42", name="Riverdale Academy")
        notification = SimpleNamespace(school_id=42)

        out = _render(notification, request)
        self.assertIn("rmc-institutional-stamp", out)
