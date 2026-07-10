"""RESILIENT_EDGE: the tenant template-marketplace templates must load their
progressive-enhancement JS.

static/js/_pages/rmc-template-marketplace.js wires two behaviours onto the
marketplace pages: an apply-confirmation guard (window.confirm before applying a
template to a live tenant, driven by data-rmc-confirm) and filter auto-submit.
The templates carried the hook attributes but no template loaded the script, so
the script was orphaned and the confirm guard was silently skipped. These tests
lock the wiring so the regression can't recur.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class TemplateMarketplaceJsWiringTests(SimpleTestCase):
    def _read(self, *parts: str) -> str:
        return (Path(settings.BASE_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_apply_confirm_loads_marketplace_js(self):
        text = self._read("templates", "marketplace", "templates_apply_confirm.html")
        self.assertIn("data-rmc-template-apply-form", text)
        self.assertIn("data-rmc-confirm", text)
        self.assertIn("_pages/rmc-template-marketplace.js", text)

    def test_browse_loads_marketplace_js(self):
        text = self._read("templates", "marketplace", "templates_browse.html")
        self.assertIn("data-rmc-template-filter-form", text)
        self.assertIn("_pages/rmc-template-marketplace.js", text)
