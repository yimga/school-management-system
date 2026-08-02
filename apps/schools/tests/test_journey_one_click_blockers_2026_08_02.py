"""
Must-fire contract for the 2026-08-02 "one-click blockers" journey work (cockpit item C).

Every readiness phase now carries a resolved ``href`` so a non-done phase is advanced
in a single click, and the launch phase deep-links to the FIRST unresolved blocker's own
fix URL. The journey-train partial renders those phase links + a one-click blockers strip.

These assert the FIXED state is present (dead-guard lesson: a negative test can pass forever
against a check that never fires — these fail before the change and stay green after).
No DB: the readiness sub-services degrade gracefully and the partial renders standalone.
"""

from types import SimpleNamespace
from unittest import mock

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from apps.schools.school_readiness import build_school_readiness


class JourneyPhaseHrefContractTests(SimpleTestCase):
    """The data layer stamps a one-click href onto every journey phase."""

    def test_every_phase_carries_an_href_key(self):
        readiness = build_school_readiness(
            SimpleNamespace(settings={}, created_at=None)
        )
        self.assertTrue(readiness.get("ok"))
        phases = readiness["phases"]
        self.assertTrue(phases, "readiness should always expose journey phases")
        for phase in phases:
            self.assertIn(
                "href",
                phase,
                f"phase {phase.get('key')!r} must carry an href for one-click routing",
            )

    def test_launch_phase_deep_links_to_first_unresolved_blocker(self):
        blocker_url = "/t/demo/studio/plan/"
        studio_payload = {
            "launch_ready": False,
            "launch_blockers": [
                {
                    "key": "plan_choice",
                    "label": "Choose plan",
                    "detail": "No plan attached",
                    "link": blocker_url,
                    "cta_label": "Resolve",
                }
            ],
        }
        with mock.patch(
            "apps.setup_studio.services.get_setup_studio_payload",
            return_value=studio_payload,
        ):
            readiness = build_school_readiness(
                SimpleNamespace(settings={}, created_at=None)
            )
        launch = next(p for p in readiness["phases"] if p["key"] == "launch")
        self.assertEqual(
            launch["href"],
            blocker_url,
            "launch phase must jump straight to the first blocker's fix URL",
        )


class JourneyTrainPartialRenderTests(SimpleTestCase):
    """The journey-train partial renders phase links + one-click resolve chips."""

    def _render(self, readiness):
        return render_to_string(
            "partials/tenant/school_readiness_journey_train.html",
            {"rmc_school_readiness": readiness},
        )

    def test_phase_links_and_blocker_resolve_links_render(self):
        readiness = {
            "ok": True,
            "meter_percent": 40,
            "provisioning_slo": {
                "label": "In progress",
                "tone": "progress",
                "time_to_value_seconds": None,
            },
            "phases": [
                {
                    "key": "configure",
                    "label": "Configured",
                    "done": False,
                    "detail": "40% activation checklist",
                    "href": "/t/demo/onboarding/",
                },
                {
                    # No href -> falls back to plain (non-link) spans.
                    "key": "operate",
                    "label": "Daily operations",
                    "done": False,
                    "detail": "unknown",
                    "href": "",
                },
            ],
            "setup_studio": {
                "launch_blockers": [
                    {
                        "key": "plan_choice",
                        "label": "Choose plan",
                        "link": "/t/demo/studio/plan/",
                        "cta_label": "Resolve",
                    },
                    {
                        # A blocker with no real link must be skipped, not rendered dead.
                        "key": "branding",
                        "label": "Import branding",
                        "link": "#",
                        "cta_label": "Resolve",
                    },
                ]
            },
        }
        html = self._render(readiness)

        # Phase with an href renders as a real one-click link.
        self.assertIn("rmc-readiness-train__phase-link", html)
        self.assertIn('data-rmc-phase-link="1"', html)
        self.assertIn('href="/t/demo/onboarding/"', html)

        # Phase without an href renders plain spans (no dead link).
        self.assertIn(">Daily operations<", html)

        # One-click blockers strip: the linkable blocker is a resolve chip...
        self.assertIn("rmc-readiness-train__blockers", html)
        self.assertIn("rmc-readiness-train__blocker", html)
        self.assertIn('href="/t/demo/studio/plan/"', html)
        self.assertIn('data-blocker-key="plan_choice"', html)
        # ...and the '#'-only blocker is filtered out, never rendered as a dead link.
        self.assertNotIn('data-blocker-key="branding"', html)

    def test_no_blockers_strip_when_none_present(self):
        readiness = {
            "ok": True,
            "meter_percent": 100,
            "provisioning_slo": {"label": "Within target", "tone": "ready"},
            "phases": [
                {
                    "key": "operate",
                    "label": "Daily operations",
                    "done": True,
                    "detail": "daily_operations",
                    "href": "/t/demo/backend/",
                }
            ],
            "setup_studio": {"launch_blockers": []},
        }
        html = self._render(readiness)
        self.assertNotIn("rmc-readiness-train__blockers", html)
