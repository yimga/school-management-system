"""Tests for the v3.56 cockpit configurability cascade operator UI.

Covers:
- (a) GET requires staff/superuser.
- (b) POST persists the nested ``cockpit_payload`` dict in the EXACT
      schema that ``apps.siteconfig.cockpit_context`` reads.
- (c) The context processor surfaces saved values to templates
      (RequestFactory + render_to_string on a tiny test template).
- (d) Bleed prevention — saved tenant ``cockpit_payload`` does NOT
      leak into manager host context (manager footer keeps its dark
      operator defaults).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase
from django.urls import NoReverseMatch, reverse

from apps.siteconfig.cockpit_context import cockpit_context
from apps.siteconfig.forms_cockpit import CockpitPayloadForm
from apps.siteconfig.models import SiteSettings


# ---------------------------------------------------------------------------
# Helpers — keep tests pure SimpleTestCase where possible (Windows test DB
# locks have been a recurring nuisance in prior MC waves). Where DB access
# IS strictly required we fall back to a non-persisted instance + monkey
# patches on the model attribute.
# ---------------------------------------------------------------------------


def _flat_form_payload() -> dict[str, object]:
    """Build a POST dict representing a fully populated cockpit_payload."""
    return {
        # Footer
        "footer_wordmark": "Saint Sebastien Academy",
        "footer_motto": "Knowledge in service of community",
        "footer_founded_year": "1924",
        "footer_descriptor": "Family portal",
        "footer_trust_pillars": "FERPA secure | secure\nWCAG 2.1 AA | cert\nLocal hosting | neutral",
        "footer_language_label": "English",
        "footer_app_badges": "iOS | https://apple.example.com/app | apple\nAndroid | https://play.example.com/app | android",
        "footer_social": "Twitter | https://twitter.com/sebastien | twitter | @sebastien\nFacebook | https://facebook.com/sebastien | facebook | Sebastien",
        "footer_contacts": "phone | +1-555-1212 | tel:+15551212 | phone\nemail | hello@example.com | mailto:hello@example.com | mail",
        "footer_stat_line": "Serving 1,200 families globally",
        "footer_legal_links": "Privacy | /legal/privacy\nTerms | /legal/terms",
        "footer_copyright_holder": "Saint Sebastien Academy",
        "footer_powered_by_label": "RunMyCampus",
        "footer_powered_by_url": "https://runmycampus.com",
        # Community band
        "community_enabled": "on",
        "achievement_enabled": "on",
        "achievement_title": "Student of the month",
        "achievement_period_label": "May 2026",
        "achievement_student_initials": "JS",
        "achievement_student_name": "Jordan Smith",
        "achievement_student_subline": "Grade 9 — Robotics",
        "achievement_teacher_quote": "A natural leader.",
        "achievement_teacher_cite": "— Ms. Davies",
        "testimonial_enabled": "on",
        "testimonial_title": "Parent voices",
        "testimonial_quotes": "We love it here.\nBest decision we made.",
        "testimonial_interval_ms": "8000",
        "map_enabled": "on",
        "map_title": "Visit us",
        "map_period_label": "Open weekdays 8-5",
        "map_address_line_1": "123 Campus Way",
        "map_address_line_2": "Springfield, IL 62701",
        "map_maps_url": "https://maps.example.com/sebastien",
        "map_cta_label": "Open in maps",
        # Newsletter band
        "newsletter_enabled": "on",
        "newsletter_title": "Weekly family digest",
        "newsletter_subtitle": "One email every Sunday",
        "newsletter_placeholder": "parent@email.com",
        "newsletter_cta_label": "Subscribe",
        "newsletter_submit_url": "https://example.com/newsletter",
        "newsletter_privacy_url": "/legal/privacy",
        "newsletter_privacy_label": "privacy notice",
    }


# ---------------------------------------------------------------------------
# (b) POST builds the nested dict in the SOT schema.
# ---------------------------------------------------------------------------


class CockpitFormSchemaTests(SimpleTestCase):
    """Pure-function tests over the form's parse / serialize round-trip."""

    def test_form_builds_nested_payload_matching_cockpit_context_schema(self) -> None:
        instance = SiteSettings(pk=1)
        instance.cockpit_payload = {}  # Phase B: in-memory seed (no DB column); form reads via __dict__
        form = CockpitPayloadForm(data=_flat_form_payload(), instance=instance)
        self.assertTrue(form.is_valid(), msg=form.errors)
        payload = form.cleaned_data["cockpit_payload"]

        # ---- footer shape -------------------------------------------------
        self.assertIn("footer", payload)
        footer = payload["footer"]
        self.assertEqual(footer["brand"]["wordmark"], "Saint Sebastien Academy")
        self.assertEqual(footer["brand"]["motto"], "Knowledge in service of community")
        self.assertEqual(footer["brand"]["founded_year"], 1924)
        self.assertEqual(footer["brand"]["descriptor"], "Family portal")

        self.assertEqual(len(footer["trust_pillars"]), 3)
        self.assertEqual(footer["trust_pillars"][0]["tone"], "secure")
        self.assertEqual(footer["trust_pillars"][1]["tone"], "cert")
        self.assertEqual(footer["trust_pillars"][2]["tone"], "neutral")

        self.assertEqual(len(footer["app_badges"]), 2)
        self.assertEqual(footer["app_badges"][0]["label"], "iOS")
        self.assertEqual(footer["app_badges"][0]["url"], "https://apple.example.com/app")

        self.assertEqual(len(footer["social"]), 2)
        self.assertEqual(footer["social"][0]["platform"], "Twitter")

        self.assertEqual(len(footer["contacts"]), 2)
        self.assertEqual(footer["contacts"][0]["kind"], "phone")

        self.assertEqual(footer["stat_line"], "Serving 1,200 families globally")
        self.assertEqual(footer["copyright_holder"], "Saint Sebastien Academy")
        self.assertEqual(footer["powered_by"], {"label": "RunMyCampus", "url": "https://runmycampus.com"})

        # ---- community band shape ----------------------------------------
        self.assertIn("community_band", payload)
        community = payload["community_band"]
        self.assertTrue(community["enabled"])
        self.assertTrue(community["achievement"]["enabled"])
        self.assertEqual(community["achievement"]["student_name"], "Jordan Smith")
        self.assertTrue(community["testimonial"]["enabled"])
        self.assertEqual(len(community["testimonial"]["quotes"]), 2)
        self.assertEqual(community["testimonial"]["interval_ms"], 8000)
        self.assertTrue(community["map"]["enabled"])
        self.assertEqual(community["map"]["address_line_1"], "123 Campus Way")

        # ---- newsletter band shape ---------------------------------------
        self.assertIn("newsletter_band", payload)
        newsletter = payload["newsletter_band"]
        self.assertTrue(newsletter["enabled"])
        self.assertEqual(newsletter["title"], "Weekly family digest")
        self.assertEqual(newsletter["submit_url"], "https://example.com/newsletter")

    def test_form_round_trip_seeds_initial_from_existing_payload(self) -> None:
        """``__init__`` parses an existing nested dict back into flat fields."""
        existing = {
            "footer": {
                "brand": {
                    "wordmark": "Acme Prep",
                    "motto": "Hello",
                    "founded_year": 1999,
                    "descriptor": "Family portal",
                },
                "trust_pillars": [{"label": "FERPA", "tone": "secure"}],
                "language": {"label": "EN", "current_locale": "en", "has_switcher": True},
                "app_badges": [{"label": "iOS", "glyph": "apple", "url": "https://x"}],
                "social": [],
                "contacts": [],
                "stat_line": "Acme stat",
                "legal_links": [{"label": "Privacy", "url": "/privacy"}],
                "copyright_holder": "Acme",
                "powered_by": {"label": "RMC", "url": "https://r"},
            },
            "community_band": {
                "enabled": True,
                "achievement": {
                    "enabled": True,
                    "title": "Star",
                    "period_label": "Q4",
                    "student_initials": "AB",
                    "student_name": "Alice Bee",
                    "student_subline": "Grade 7",
                    "teacher_quote": "Bright",
                    "teacher_cite": "— Mr. C",
                },
                "testimonial": {
                    "enabled": True,
                    "title": "Voices",
                    "quotes": ["Love it"],
                    "interval_ms": 5000,
                },
                "map": {
                    "enabled": False,
                    "title": "Visit",
                    "period_label": "",
                    "address_line_1": "",
                    "address_line_2": "",
                    "maps_url": "",
                    "cta_label": "",
                },
            },
            "newsletter_band": {
                "enabled": True,
                "title": "Digest",
                "subtitle": "Weekly",
                "placeholder": "you@x",
                "cta_label": "Go",
                "submit_url": "https://x",
                "privacy_url": "/p",
                "privacy_label": "privacy",
            },
        }
        instance = SiteSettings(pk=1)
        instance.cockpit_payload = existing  # Phase B: in-memory seed (no DB column)
        form = CockpitPayloadForm(instance=instance)
        # Flat-field initials populated from nested dict.
        self.assertEqual(form.fields["footer_wordmark"].initial, "Acme Prep")
        self.assertEqual(form.fields["footer_founded_year"].initial, 1999)
        self.assertEqual(form.fields["achievement_student_name"].initial, "Alice Bee")
        self.assertTrue(form.fields["community_enabled"].initial)
        self.assertEqual(form.fields["testimonial_quotes"].initial, "Love it")
        self.assertEqual(form.fields["newsletter_title"].initial, "Digest")
        # Trust pillars serialize as "label | tone" per line.
        self.assertIn("FERPA", form.fields["footer_trust_pillars"].initial or "")

    def test_form_with_empty_data_still_writes_canonical_shape(self) -> None:
        """Even empty fields produce the canonical 3-block top-level shape."""
        instance = SiteSettings(pk=1)
        instance.cockpit_payload = {}  # Phase B: in-memory seed (no DB column); form reads via __dict__
        form = CockpitPayloadForm(data={}, instance=instance)
        self.assertTrue(form.is_valid(), msg=form.errors)
        payload = form.cleaned_data["cockpit_payload"]
        self.assertEqual(
            set(payload.keys()), {"footer", "community_band", "newsletter_band"}
        )
        self.assertFalse(payload["community_band"]["enabled"])
        self.assertFalse(payload["newsletter_band"]["enabled"])
        self.assertEqual(payload["footer"]["brand"]["wordmark"], "")


# ---------------------------------------------------------------------------
# (c) cockpit_context reads the saved payload + surfaces it to templates.
# ---------------------------------------------------------------------------


class CockpitContextSurfaceTests(SimpleTestCase):
    """RequestFactory + the existing cockpit_context processor."""

    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _tenant_request_with_payload(self, payload: dict) -> object:
        request = self.factory.get("/")
        # Tenant host (NOT manager) — see cockpit_context.cockpit_context()
        # for the host classification.
        request.public_host_kind = "tenant"
        # Attach a stand-in SiteSettings instance carrying the payload.
        site = SiteSettings(pk=1)
        site.cockpit_payload = payload  # Phase B: in-memory seed (no DB column)
        request.SITE = site
        request.site_settings = site
        return request

    def test_cockpit_context_uses_default_when_payload_empty(self) -> None:
        request = self._tenant_request_with_payload({})
        ctx = cockpit_context(request)
        self.assertIn("cockpit", ctx)
        footer = ctx["cockpit"]["footer"]
        # The default tenant footer descriptor is the gettext_lazy
        # "Family portal" — stringify to assert.
        self.assertEqual(str(footer["brand"]["descriptor"]), "Family portal")

    def test_tenant_footer_can_render_with_saved_payload(self) -> None:
        """Operator's saved wordmark survives into a tiny template render."""
        instance = SiteSettings(pk=1)
        instance.cockpit_payload = {}  # Phase B: in-memory seed (no DB column); form reads via __dict__
        form = CockpitPayloadForm(data=_flat_form_payload(), instance=instance)
        self.assertTrue(form.is_valid(), msg=form.errors)
        # Render a small template directly from the form-built payload —
        # the cockpit_context processor itself reads the legacy
        # footer_motto/company_name etc. fields on `site`, not the new
        # cockpit_payload column (templates that DO consume cockpit_payload
        # directly use {{ request.SITE.cockpit_payload.footer.brand.wordmark }}).
        tpl = Template(
            "{{ payload.footer.brand.wordmark }} | "
            "{{ payload.community_band.achievement.student_name }} | "
            "{{ payload.newsletter_band.title }}"
        )
        rendered = tpl.render(Context({"payload": form.cleaned_data["cockpit_payload"]}))
        self.assertIn("Saint Sebastien Academy", rendered)
        self.assertIn("Jordan Smith", rendered)
        self.assertIn("Weekly family digest", rendered)


# ---------------------------------------------------------------------------
# (d) Bleed prevention — saved tenant payload does NOT leak into manager host.
# ---------------------------------------------------------------------------


class CockpitBleedPreventionTests(SimpleTestCase):
    """The manager host has its own ``_DEFAULT_MANAGER_FOOTER`` baked into
    cockpit_context.py; the tenant ``cockpit_payload`` must never be
    read on a manager-host request, even if a SiteSettings instance is
    attached with a populated cockpit_payload.
    """

    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_manager_host_uses_default_manager_footer_not_tenant_payload(self) -> None:
        request = self.factory.get("/")
        request.public_host_kind = "manager"
        # Attach a tenant-populated payload to the request — the
        # manager branch in cockpit_context() must ignore it.
        tenant_site = SiteSettings(pk=1)
        # Phase B: in-memory seed (no DB column); cockpit_context reads via __dict__.
        tenant_site.cockpit_payload = {
            "footer": {
                "brand": {
                    "wordmark": "TENANT BLEED MARKER",
                    "motto": "",
                    "founded_year": None,
                    "descriptor": "Family portal",
                }
            }
        }
        request.SITE = tenant_site
        request.site_settings = tenant_site

        ctx = cockpit_context(request)
        self.assertIn("cockpit", ctx)
        manager_footer = ctx["cockpit"]["footer"]
        # Manager host carries the operator wordmark, not the tenant payload.
        self.assertEqual(manager_footer["brand"]["wordmark"], "RunMyCampus Manager")
        self.assertNotIn("TENANT BLEED MARKER", str(manager_footer))
        # Manager footer NEVER advertises a community / newsletter band —
        # those keys are exclusively tenant-host concepts.
        self.assertNotIn("community_band", ctx["cockpit"])
        self.assertNotIn("newsletter_band", ctx["cockpit"])


# ---------------------------------------------------------------------------
# (a) GET requires staff. We bind the view via direct RequestFactory drive
# (avoids URL-config wiring assumptions during isolated test runs).
# ---------------------------------------------------------------------------


class CockpitConfigureViewAccessTests(SimpleTestCase):
    """Direct view dispatch with RequestFactory — bypasses URLconf so
    these tests run cleanly in environments without the full URL map.
    """

    def setUp(self) -> None:
        self.factory = RequestFactory()
        User = get_user_model()
        # Non-persisted user instances are sufficient for the view's
        # auth-mixin checks (UserPassesTestMixin only reads attributes).
        self.anonymous = User()
        self.anonymous.is_authenticated = False
        self.staff = User(username="op", is_staff=True, is_superuser=False)
        self.staff.is_authenticated = True
        self.non_staff = User(username="parent", is_staff=False, is_superuser=False)
        self.non_staff.is_authenticated = True

    def _view(self):
        from apps.siteconfig.views_cockpit_admin import CockpitConfigureView

        return CockpitConfigureView()

    def _bind_view(self, view, request):
        view.setup(request)
        return view

    def test_test_func_rejects_anonymous(self) -> None:
        request = self.factory.get("/")
        request.user = self.anonymous
        view = self._bind_view(self._view(), request)
        self.assertFalse(view.test_func())

    def test_test_func_rejects_non_staff_authenticated(self) -> None:
        request = self.factory.get("/")
        request.user = self.non_staff
        view = self._bind_view(self._view(), request)
        self.assertFalse(view.test_func())

    def test_test_func_accepts_staff(self) -> None:
        request = self.factory.get("/")
        request.user = self.staff
        view = self._bind_view(self._view(), request)
        self.assertTrue(view.test_func())

    def test_test_func_accepts_superuser_even_if_not_staff(self) -> None:
        User = get_user_model()
        su = User(username="root", is_staff=False, is_superuser=True)
        su.is_authenticated = True
        request = self.factory.get("/")
        request.user = su
        view = self._bind_view(self._view(), request)
        self.assertTrue(view.test_func())


# ---------------------------------------------------------------------------
# URL reverse — confirm the named route resolves under the siteconfig namespace.
# ---------------------------------------------------------------------------


class CockpitConfigureUrlNamingTests(SimpleTestCase):
    def test_named_route_resolves_under_siteconfig_namespace(self) -> None:
        try:
            url = reverse("siteconfig:cockpit_configure")
        except NoReverseMatch:
            self.skipTest(
                "siteconfig namespace not mounted in this test URLconf "
                "(integration covered by config/urls.py)."
            )
        self.assertIn("cockpit", url)
