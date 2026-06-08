"""Creative web-address suggestions for the signup form (2026-06-08).

Owner: the web address inherited the full school name verbatim, however long.
Instead, offer a few short, memorable, pickable options ("smart & short"):
lead with the anchor word, then clean variants, full slug last as a fallback.

Covers: the pure generator (build_slug_suggestions, no DB), the live endpoint
(availability-aware, available-first), and — critically — that both the new
suggest route AND the pre-existing slug-check route resolve on the PUBLIC host
(they were absent from config.public_urls, so the live check silently 404'd in
prod; the suggestions would have done the same).
"""

from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School
from apps.schools.signup_views import build_slug_suggestions


class BuildSlugSuggestionsTests(TestCase):
    def test_leads_with_anchor_then_short_variants(self):
        out = build_slug_suggestions("Greenfield International Academy")
        # Most memorable handle first; type-word and abbreviated variants next.
        self.assertEqual(out[0], "greenfield")
        self.assertIn("greenfield-academy", out)
        self.assertIn("greenfieldacademy", out)
        self.assertIn("greenfield-intl", out)  # "international" -> "intl"
        # Full verbatim slug is offered, but never first.
        self.assertIn("greenfield-international-academy", out)
        self.assertNotEqual(out[0], "greenfield-international-academy")

    def test_single_word_name_yields_one_clean_option(self):
        out = build_slug_suggestions("Greenfield")
        self.assertEqual(out, ["greenfield"])

    def test_type_word_name(self):
        out = build_slug_suggestions("Cedar School")
        self.assertEqual(out[0], "cedar")
        self.assertIn("cedar-school", out)
        self.assertIn("cedarschool", out)

    def test_saint_prefix_stays_glued(self):
        out = build_slug_suggestions("St Mary's Catholic High School")
        self.assertEqual(out[0], "st-marys")

    def test_country_code_adds_tagged_option(self):
        out = build_slug_suggestions("Greenfield Academy", country_code="KE")
        self.assertIn("greenfield-ke", out)

    def test_reserved_anchor_is_excluded(self):
        # "Admin" -> anchor "admin" + full "admin" are both reserved -> nothing.
        self.assertEqual(build_slug_suggestions("Admin"), [])

    def test_empty_name_is_empty(self):
        self.assertEqual(build_slug_suggestions(""), [])
        self.assertEqual(build_slug_suggestions("   "), [])

    def test_no_duplicates(self):
        out = build_slug_suggestions("Greenfield International Academy")
        self.assertEqual(len(out), len(set(out)))


@override_settings(RATELIMIT_ENABLE=False)
class SignupSlugSuggestEndpointTests(TestCase):
    def _get(self, **params):
        resp = self.client.get(reverse("signup_slug_suggest"), params)
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def test_returns_available_suggestions(self):
        data = self._get(name="Greenfield International Academy")
        self.assertEqual(data["name"], "Greenfield International Academy")
        slugs = [s["slug"] for s in data["suggestions"]]
        self.assertTrue(slugs)
        self.assertLessEqual(len(slugs), 4)
        self.assertTrue(all(s["available"] for s in data["suggestions"]))
        self.assertEqual(slugs[0], "greenfield")

    def test_taken_options_sink_below_available(self):
        School.objects.create(
            name="Existing", slug="greenfield", subdomain="greenfield",
            is_active=False, country_code="US",
        )
        data = self._get(name="Greenfield International Academy")
        first = data["suggestions"][0]
        # The cleanest free option leads; the taken anchor is not preselected.
        self.assertTrue(first["available"])
        self.assertNotEqual(first["slug"], "greenfield")

    def test_blank_name_returns_no_suggestions(self):
        data = self._get(name="")
        self.assertEqual(data["suggestions"], [])

    def test_reserved_name_returns_no_suggestions(self):
        data = self._get(name="admin")
        self.assertEqual(data["suggestions"], [])


class SignupSlugRoutesPublicHostTests(TestCase):
    """The signup form renders on the PUBLIC host, so its live helper endpoints
    must resolve under config.public_urls — not only the monolithic config.urls.
    slug-check was missing there (silent 404 in prod); this pins both routes."""

    @override_settings(ROOT_URLCONF="config.public_urls")
    def test_both_helper_routes_resolve_on_public_host(self):
        self.assertEqual(reverse("signup_slug_suggest"), "/signup/slug-suggest/")
        self.assertEqual(reverse("signup_slug_check"), "/signup/slug-check/")
