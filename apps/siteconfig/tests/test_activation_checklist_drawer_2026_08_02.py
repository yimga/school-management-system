"""
Must-fire contract for the 2026-08-02 activation-checklist slide-over (cockpit item B).

The "Open full activation checklist" CTA opens the checklist in an rmc-sheet side drawer
via a chrome-less fragment (siteconfig:onboarding_fragment), with the CTA's href staying
the no-JS / fetch-failure fallback. These lock: the fragment endpoint is wired, the
fragment renders real steps, and the setup surface wires the drawer + its script.
"""

from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.urls import resolve, reverse

REPO = Path(settings.BASE_DIR)


class ChecklistFragmentEndpointTests(SimpleTestCase):
    def test_fragment_url_resolves_to_the_fragment_view(self):
        url = reverse("siteconfig:onboarding_fragment", urlconf="config.tenant_urls")
        match = resolve(url, urlconf="config.tenant_urls")
        self.assertEqual(
            match.func.__name__, "school_activation_onboarding_fragment"
        )


class ChecklistFragmentRenderTests(SimpleTestCase):
    def _render(self, onboarding):
        return render_to_string(
            "partials/tenant/activation_checklist_fragment.html",
            {"onboarding": onboarding},
        )

    def test_renders_steps_progress_and_action_links(self):
        onboarding = {
            "percent": 50,
            "completed": 1,
            "total": 2,
            "display_steps": [
                {
                    "key": "roster",
                    "label": "Import your roster",
                    "description": "Bring in students and staff.",
                    "done": False,
                    "link": "/t/demo/import/",
                },
                {
                    "key": "brand",
                    "label": "Set your brand",
                    "description": "Logo and colors.",
                    "done": True,
                    "link": "/t/demo/brand/",
                },
            ],
        }
        html = self._render(onboarding)
        self.assertIn("Import your roster", html)
        self.assertIn("Set your brand", html)
        self.assertIn('href="/t/demo/import/"', html)
        self.assertIn("progress-bar", html)
        self.assertIn('data-step-key="roster"', html)
        # Incomplete step invites "Start"; completed step invites "Review".
        self.assertIn("Start", html)
        self.assertIn("Review", html)

    def test_empty_state_when_no_steps(self):
        html = self._render({"total": 0, "display_steps": []})
        self.assertNotIn("progress-bar", html)
        self.assertIn("checklist will appear here", html)


class SetupSurfaceWiresDrawerTests(SimpleTestCase):
    """The Admin Home setup surface wires the drawer trigger, dialog, and script."""

    def test_setup_surface_markup_wires_the_slide_over(self):
        src = (
            REPO / "templates/partials/tenant/setup_command_surface.html"
        ).read_text(encoding="utf-8")
        # Trigger is progressively enhanced but keeps a real href fallback.
        self.assertIn('data-rmc-checklist-drawer="1"', src)
        self.assertIn("siteconfig:onboarding_fragment", src)
        self.assertIn('aria-controls="rmc-activation-checklist-sheet"', src)
        # The rmc-sheet side drawer + close affordance exist.
        self.assertIn('id="rmc-activation-checklist-sheet"', src)
        self.assertIn("rmc-sheet--side-end", src)
        self.assertIn("data-rmc-sheet-close", src)
        # The enhancement script is loaded.
        self.assertIn("js/rmc-activation-checklist-drawer.js", src)

    def test_checklist_cta_is_still_a_real_button_with_href_fallback(self):
        src = (
            REPO / "templates/partials/tenant/setup_command_surface.html"
        ).read_text(encoding="utf-8")
        # Regression guard for cockpit item's real-button fix + no-JS navigation.
        self.assertIn('class="rmc-setup-surface__all"', src)
        self.assertIn('href="{{ rmc_setup_checklist_url }}"', src)
        self.assertIn("bi-check2-square", src)
