"""T5b: the tenant login page shows the SCHOOL's name (not a generic literal).

The tenant login (``auth/login.html``) already rendered the school's logo, colors,
and wallpaper via the pre-auth brand cascade. T5b closes the last gap: the browser
``<title>`` and the sign-in card title fall back to the school's own name (a safe
``LOGIN_SCHOOL_NAME`` context var) instead of the generic "School portal" — and do
so without 500-ing on the base host where ``request.school`` is ``None``.
"""

from __future__ import annotations

import re

from django.test import TestCase
from django.urls import reverse

from apps.schools.models import School


def _title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return (m.group(1) if m else "").strip()


class LoginTitleBrandingTests(TestCase):
    def _bind_school(self, school):
        session = self.client.session
        session["school_id"] = str(school.id)
        session.save()

    def test_title_and_card_show_school_name(self):
        school = School.objects.create(
            name="Tinker Test High",
            subdomain="tinker-test-branding",
            slug="tinker-test-branding",
            is_active=True,
        )
        self._bind_school(school)
        resp = self.client.get(reverse("accounts:login"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8", "replace")
        # Browser tab title is now school-aware (was the generic "School portal login").
        self.assertIn("Tinker Test High", _title(html))
        # And the school name renders on the page (card title / preview).
        self.assertContains(resp, "Tinker Test High")

    def test_base_host_no_tenant_does_not_500(self):
        # No school bound (anonymous visitor on the base host): the template must
        # NOT raise VariableDoesNotExist on ``request.school.name`` — LOGIN_SCHOOL_NAME
        # is always a plain string. The regression this guards is a hard 500; the
        # title still renders through the block (ends with our "· Sign in" suffix).
        resp = self.client.get(reverse("accounts:login"))
        self.assertEqual(resp.status_code, 200)  # was a VariableDoesNotExist 500
        self.assertIn("Sign in", _title(resp.content.decode("utf-8", "replace")))
