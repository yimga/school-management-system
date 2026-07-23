"""Email/SMS CTA links must be real absolute URLs, not the dead ``#``.

``settings.BASE_URL`` was never defined in any deployment, so every
``hasattr(settings, "BASE_URL")``-guarded link in the notification service
silently rendered ``#`` (a dead button in the daily deadline-reminder email) or
a host-less relative path. These fire against the pre-fix code.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.evals.notifications import _tenant_portal_link
from apps.schools.models import School


class TenantPortalLinkTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Oak Academy", slug="oak-links", subdomain="oak-links", is_active=True
        )

    def test_link_is_absolute_not_a_dead_hash(self):
        link = _tenant_portal_link(self.school, "/evals/teacher/marks/entry/")
        self.assertNotEqual(link, "#")
        self.assertTrue(link.startswith("https://"), link)
        self.assertIn("/evals/teacher/marks/entry/", link)
        self.assertIn("oak-links", link)  # scoped to the school's own host

    def test_missing_school_degrades_to_relative_not_hash(self):
        # A dead "#" goes nowhere; a bare path at least resolves on-host.
        link = _tenant_portal_link(None, "/portal/results/1/")
        self.assertNotEqual(link, "#")
        self.assertTrue(link.startswith("/portal/results/"), link)

    @override_settings(BASE_URL="https://ops.example.com")
    def test_operator_base_url_override_wins(self):
        link = _tenant_portal_link(self.school, "/evals/teacher/marks/entry/")
        self.assertEqual(link, "https://ops.example.com/evals/teacher/marks/entry/")

    def test_deadline_reminder_context_link_is_live(self):
        # End-to-end through the service: the entry_link handed to the template
        # is a real link, so the "Enter grades" button is not dead.
        from datetime import timedelta

        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from apps.people.models import TeacherProfile

        User = get_user_model()
        user = User.objects.create_user(
            username="tlink", email="t@example.com", password="pass12345678"
        )
        teacher = TeacherProfile.objects.create(user=user, school=self.school)

        captured = {}
        from apps.evals import notifications as notif_mod

        original = notif_mod.render_to_string

        def _spy(template_name, context=None, *a, **k):
            if template_name == "emails/deadline_reminder.html":
                captured["entry_link"] = (context or {}).get("entry_link")
            return original(template_name, context, *a, **k)

        notif_mod.render_to_string = _spy
        try:
            notif_mod.NotificationService().send_deadline_reminder_email(
                teacher, timezone.now() + timedelta(days=2), 3
            )
        finally:
            notif_mod.render_to_string = original

        self.assertIn("entry_link", captured)
        self.assertNotEqual(captured["entry_link"], "#")
        self.assertTrue(str(captured["entry_link"]).startswith("https://"))
