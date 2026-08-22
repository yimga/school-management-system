"""An empty cockpit section must not leave an empty expandable behind.

``partials/cockpit/_collapsable_section.html`` rendered its ``<details>``, summary and
rule unconditionally, while every inner partial self-gated on
``cockpit.<section>.enabled`` plus a non-empty data list. A section with nothing to say
therefore produced a bordered strip with no content. The founder dashboard stacks ten of
them and showed SEVEN empty rules above its first real block -- which is what an
operator reported as "a section with lines and empty".

The wrapper's own docstring named the problem and pushed the fix onto callers ("gate the
include itself"). None of the 42 call sites did, and a caller-side gate cannot be written
correctly anyway: the wrapper key (``founder__tenant_heatmap``) is not the cockpit key
(``tenant_heatmap``), and "enabled" is only half the condition.
"""
from django.template import Context, Template
from django.test import SimpleTestCase

from apps.platform_runtime.templatetags.collapsable_tags import has_visible_output

WRAPPER = (
    '{% include "partials/cockpit/_collapsable_section.html" with '
    'title="Tenant heatmap" key="t__heatmap" include_partial=partial %}'
)


class HasVisibleOutputTests(SimpleTestCase):
    def test_whitespace_is_nothing(self):
        self.assertFalse(has_visible_output("\n   \n\t"))

    def test_html_comment_is_nothing(self):
        self.assertFalse(has_visible_output("\n<!-- disabled -->\n"))

    def test_lone_scanner_sentinel_is_nothing(self):
        self.assertFalse(
            has_visible_output(
                '<div class="visually-hidden rmc-empty-state-sentinel" '
                'aria-hidden="true"></div>'
            )
        )

    def test_real_markup_survives(self):
        self.assertTrue(has_visible_output('<div class="card">Anything</div>'))

    def test_a_deliberate_empty_state_card_survives(self):
        # A partial that CHOOSES to render an empty state is real content and is kept.
        self.assertTrue(has_visible_output('<p class="text-muted">No tenants yet.</p>'))


class CollapsableSectionRenderTests(SimpleTestCase):
    def _render(self, partial):
        return Template("{% load i18n %}" + WRAPPER).render(
            Context({"partial": partial})
        )

    def test_section_that_renders_nothing_emits_no_details(self):
        html = self._render("partials/cockpit/tests_fixture_empty.html")
        self.assertNotIn("<details", html)
        self.assertNotIn("Tenant heatmap", html)

    def test_section_with_content_still_renders(self):
        html = self._render("partials/cockpit/tests_fixture_content.html")
        self.assertIn("<details", html)
        self.assertIn("Tenant heatmap", html)
        self.assertIn("REAL-CONTENT", html)

    def test_dashboard_pack_hidden_sections_still_wins(self):
        html = Template("{% load i18n %}" + WRAPPER).render(
            Context(
                {
                    "partial": "partials/cockpit/tests_fixture_content.html",
                    "dashboard_pack_hidden_sections": ["t__heatmap"],
                }
            )
        )
        self.assertNotIn("<details", html)
