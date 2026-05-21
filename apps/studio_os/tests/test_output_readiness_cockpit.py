"""Studio OS — Output readiness cockpit (v3.54.0, 2026-05-21).

Agent 4 of the next-realm fan-out: tests that the Output mode renders the
readiness cockpit, honest service-state badges, real-route tile links, and
respects layout-safety + a11y guards.

These tests deliberately exercise template grammar (string scans), not view
internals, so the suite stays fast and resilient to copy churn. They do NOT
execute system migrations beyond the default Django test setup.
"""

from __future__ import annotations

import re

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.reports.models import ReportPack


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"]
)
class OutputReadinessCockpitTests(TestCase):
    """Tenant-host render of the readiness cockpit + layout-safety scans."""

    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_superuser(
            username="output_readiness_op",
            email="orop@example.com",
            password="testpass123",
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.operator)
        self.url = reverse("studio_os:output")

    # ------------------------------------------------------------------
    # 1. Page renders for operator (tenant default host)
    # ------------------------------------------------------------------
    def test_output_page_renders_for_operator(self):
        response = self.client.get(self.url + "?pane=dependency")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-rmc-output-cockpit="1"')

    def test_output_page_renders_for_operator_on_manager_host(self):
        c = Client(HTTP_HOST="manager.runmycampus.com")
        c.force_login(self.operator)
        response = c.get(self.url + "?pane=dependency")
        self.assertEqual(response.status_code, 200)

    # ------------------------------------------------------------------
    # 2. Readiness tiles render — derived from real packs OR honest unknown
    # ------------------------------------------------------------------
    def test_readiness_tiles_render_with_no_packs_shows_unknown(self):
        ReportPack.objects.all().delete()
        response = self.client.get(self.url + "?pane=dependency")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-output-tiles")
        # Honest fallback — at least one tile in "Unknown" state.
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn('data-state="unknown"', body)

    def test_readiness_tiles_render_real_counts_when_packs_exist(self):
        ReportPack.objects.create(
            code="readiness-pack-a",
            name="Readiness Pack A",
            dependency_schema={"templates": ["alpha", "beta"]},
            sample_data_config={
                "title": "Readiness sample",
                "rows": [{"label": "Average", "value": "13/20"}],
            },
            is_active=True,
        )
        response = self.client.get(self.url + "?pane=dependency")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        # Reports tile reads "1" from output_dependency_graph|length.
        self.assertIn('data-output-tile="reports"', body)
        self.assertIn('rmc-output-tile__count', body)
        # Derived service state must be present when packs exist.
        self.assertIn('data-state="online"', body)

    # ------------------------------------------------------------------
    # 3. Iframes have title=
    # ------------------------------------------------------------------
    def test_iframes_have_title_attribute(self):
        """Any <iframe> rendered by Output partials must have a title= for a11y."""
        for pane in ("dependency", "reports", "branding", "policy", "credentials"):
            with self.subTest(pane=pane):
                response = self.client.get(self.url + f"?pane={pane}")
                self.assertEqual(response.status_code, 200)
                body = response.content.decode("utf-8", errors="replace")
                # Find every iframe and confirm title= present on each.
                for m in re.finditer(r"<iframe\b[^>]*>", body, re.IGNORECASE):
                    iframe_tag = m.group(0)
                    self.assertRegex(
                        iframe_tag,
                        r"\btitle\s*=\s*[\"']",
                        msg=(
                            f"iframe in pane={pane!r} missing title= attribute: "
                            f"{iframe_tag!r}"
                        ),
                    )

    # ------------------------------------------------------------------
    # 4. No fixed-pixel width on output wrappers (string scan)
    # ------------------------------------------------------------------
    def test_no_fixed_pixel_width_on_output_wrappers(self):
        """Layout safety: outputs must not carry inline style="width: <N>px"."""
        for pane in ("dependency", "reports", "branding", "policy", "credentials"):
            with self.subTest(pane=pane):
                response = self.client.get(self.url + f"?pane={pane}")
                body = response.content.decode("utf-8", errors="replace")
                # Look for any style="width: 999px" or style="width:999px".
                hits = re.findall(
                    r'style\s*=\s*"[^"]*\bwidth\s*:\s*\d+(?:\.\d+)?\s*px',
                    body,
                    re.IGNORECASE,
                )
                self.assertEqual(
                    hits,
                    [],
                    msg=(
                        f"Fixed-pixel widths found on pane={pane!r}: {hits[:3]!r}. "
                        "Use 100% / max-width / clamp-height instead."
                    ),
                )

    # ------------------------------------------------------------------
    # 5. No dummy href="#" links in readiness/preview pane partials
    # ------------------------------------------------------------------
    def test_no_dummy_hash_links_in_readiness_cockpit(self):
        """Real-routes-or-hidden rule: nothing in the cockpit may href="#"."""
        response = self.client.get(self.url + "?pane=dependency")
        body = response.content.decode("utf-8", errors="replace")
        # Restrict the scan to the cockpit section itself; anchor scroll
        # targets elsewhere in the shell (like skip-links) are out of scope.
        match = re.search(
            r'data-rmc-output-cockpit="1".*?</section>',
            body,
            re.DOTALL,
        )
        self.assertIsNotNone(
            match, msg="Readiness cockpit section not found in dependency pane."
        )
        cockpit_block = match.group(0)
        self.assertNotIn(
            'href="#"',
            cockpit_block,
            msg="Readiness cockpit must not contain dummy href=\"#\" links.",
        )

    # ------------------------------------------------------------------
    # 6. Long output titles wrap (no white-space:nowrap on titles)
    # ------------------------------------------------------------------
    def test_long_output_titles_wrap(self):
        """Layout safety: readiness preview titles must allow wrapping."""
        ReportPack.objects.create(
            code="rdy-very-long-pack-name-for-wrap-test",
            name=(
                "A_very_long_unbroken_pack_name_used_to_assert_overflow_wrap_"
                "behavior_in_the_readiness_preview_pane_layer"
            ),
            dependency_schema={"templates": ["x"]},
            sample_data_config={
                "title": (
                    "A_very_long_unbroken_preview_title_that_must_wrap_inside_"
                    "the_preview_card_grid_otherwise_horizontal_overflow_breaks_"
                    "the_workspace_canvas"
                ),
                "rows": [{"label": "Sample", "value": "OK"}],
            },
            is_active=True,
        )
        response = self.client.get(self.url + "?pane=dependency")
        body = response.content.decode("utf-8", errors="replace")
        # Title class is on the cockpit; CSS rule allows wrap. Confirm the
        # class hook is present so the rule applies.
        self.assertIn("rmc-output-preview__title", body)
        # Confirm we did NOT emit inline white-space:nowrap on titles.
        self.assertNotIn("white-space: nowrap", body)
        self.assertNotIn("white-space:nowrap", body)

    # ------------------------------------------------------------------
    # 7. Readiness service-state badge is honest
    # ------------------------------------------------------------------
    def test_readiness_service_state_is_honest(self):
        """Cockpit declares 'online' (live or derived) or 'offline' — never both."""
        response = self.client.get(self.url + "?pane=dependency")
        body = response.content.decode("utf-8", errors="replace")
        # Pull only the cockpit block, count badge occurrences inside.
        match = re.search(
            r'data-rmc-output-cockpit="1".*?</section>',
            body,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        block = match.group(0)
        online_hits = block.count('rmc-output-cockpit__service-state" data-state="online"')
        offline_hits = block.count('rmc-output-cockpit__service-state" data-state="offline"')
        self.assertEqual(
            online_hits + offline_hits,
            1,
            msg=(
                "Exactly one service-state badge expected on the cockpit header, "
                f"got online={online_hits} offline={offline_hits}."
            ),
        )

    # ------------------------------------------------------------------
    # 8. Mobile tabs wrap fallback class present
    # ------------------------------------------------------------------
    def test_mobile_tabs_have_wrap_fallback_class(self):
        response = self.client.get(self.url + "?pane=dependency")
        self.assertContains(response, "rmc-output-mobile-tabs")

    # ------------------------------------------------------------------
    # 9. Branding inheritance pane shows the chain + swatches
    # ------------------------------------------------------------------
    def test_branding_pane_shows_token_swatches_and_chain(self):
        response = self.client.get(self.url + "?pane=branding")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-output-brand-swatches")
        self.assertContains(response, "--school-primary")
        self.assertContains(response, "rmc-output-brand-chain__step")

    # ------------------------------------------------------------------
    # 10. Policy pane uses responsive list grammar
    # ------------------------------------------------------------------
    def test_policy_pane_uses_responsive_list_grammar(self):
        response = self.client.get(self.url + "?pane=policy")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rmc-output-policy-list")
