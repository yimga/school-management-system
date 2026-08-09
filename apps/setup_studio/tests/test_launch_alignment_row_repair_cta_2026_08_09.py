"""The Launch/Setup "Registry alignment" table must render each *mismatched* row's
OWN focused repair CTA (``repair_field=<key>#repair-editor``), so a tenant opens the
exact editor for that field — e.g. Education system — instead of being dumped on the
shared country hub.

Each row dict already carried a ``cta_url`` (built by ``_registry_field_cta`` and
locked by ``apps.platform_runtime.tests.test_remedy_click_contract``), but the launch
template rendered only ``label``/``value``/an OK-or-warning icon — the per-field CTA
was dead data and every finding fell back to the shared ``settings_cta``
(``repair_field=country``). These tests fail on that old template and pass once the
row loop renders ``row.cta_url`` for ``not row.ok`` rows.
"""

from django.template.loader import render_to_string
from django.test import SimpleTestCase

TEMPLATE = "studio_os/partials/launch_studio_overview_body.html"


class LaunchAlignmentRowRepairCtaRenderTests(SimpleTestCase):
    def _render(self, key_rows, mismatch_count):
        # A deliberately minimal launch_payload: the partial resolves every other
        # key it touches to '' (harmless), and the launch-ready include is skipped
        # because launch_ready is absent/falsy.
        payload = {
            "registry_alignment": {
                "mismatch_count": mismatch_count,
                "key_rows": key_rows,
                # The shared CTA is intentionally the country hub — the point of the
                # per-row links is that findings no longer depend on it.
                "settings_cta": {
                    "label": "Fix in settings",
                    "url": "/school/configuration/?repair_field=country#repair-editor",
                },
                "summary_lines": [],
                "detail": "",
            }
        }
        return render_to_string(TEMPLATE, {"launch_payload": payload})

    def test_mismatched_education_system_row_renders_its_own_repair_link(self):
        html = self._render(
            key_rows=[
                {
                    "key": "education_system",
                    "label": "Education system",
                    "value": "— (IB)",
                    "ok": False,
                    "cta_url": "/school/configuration/?repair_field=education_system#repair-editor",
                },
            ],
            mismatch_count=1,
        )
        # The mismatched finding links directly to ITS editor, not the country hub.
        self.assertIn("repair_field=education_system#repair-editor", html)

    def test_ok_row_does_not_render_a_per_field_repair_link(self):
        # timezone is chosen because it is NOT the shared settings_cta field
        # (country) — so if repair_field=timezone appears, it can only be the
        # per-row link, which must be suppressed for an aligned (ok) row.
        html = self._render(
            key_rows=[
                {
                    "key": "timezone",
                    "label": "Timezone",
                    "value": "Coordinated Universal Time (UTC)",
                    "ok": True,
                    "cta_url": "/school/configuration/?repair_field=timezone#repair-editor",
                },
            ],
            mismatch_count=0,
        )
        self.assertNotIn("repair_field=timezone", html)

    def test_only_the_mismatched_row_of_a_mixed_set_gets_a_link(self):
        html = self._render(
            key_rows=[
                {
                    "key": "timezone",
                    "label": "Timezone",
                    "value": "Coordinated Universal Time (UTC)",
                    "ok": True,
                    "cta_url": "/school/configuration/?repair_field=timezone#repair-editor",
                },
                {
                    "key": "education_system",
                    "label": "Education system",
                    "value": "— (IB)",
                    "ok": False,
                    "cta_url": "/school/configuration/?repair_field=education_system#repair-editor",
                },
            ],
            mismatch_count=1,
        )
        self.assertIn("repair_field=education_system#repair-editor", html)
        self.assertNotIn("repair_field=timezone", html)
