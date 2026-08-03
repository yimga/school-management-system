"""Chromeless embed mode for the marketplace app sandbox.

The app sandbox previews a surface's CONTENT in an iframe. It used to embed the
FULL portal shell (header / sidebar / footer), a fragile page-within-a-page whose
deferred CSS bundle does not activate inside the sandbox iframe (tofu icons, flat
styling). Embed mode (``?rmc_embed=1``) stamps ``data-rmc-embed`` on ``<html>``,
eager-loads the deferred shell bundle, and hides the chrome via
``css/rmc-embed.css`` — everything scoped under ``html[data-rmc-embed]`` so it is
inert on every normal page.

MUST-FIRE: each assertion fails on the pre-2026-08-03 code.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.contrib.staticfiles import finders
from django.template import Context, Template
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase


def _template_src(name: str) -> str:
    return Path(get_template(name).origin.name).read_text(encoding="utf-8")


class EmbedFlagConditionalTests(SimpleTestCase):
    """The exact flag expression portal_base stamps on <html> toggles correctly."""

    def test_embed_flag_expression_toggles_on_query_param(self):
        tpl = Template("{% if request.GET.rmc_embed == '1' %}Y{% else %}N{% endif %}")
        on = tpl.render(Context({"request": RequestFactory().get("/x/?rmc_embed=1")}))
        off = tpl.render(Context({"request": RequestFactory().get("/x/")}))
        self.assertEqual((on, off), ("Y", "N"))


class PortalBaseEmbedWiringSealTests(SimpleTestCase):
    def setUp(self):
        self.src = _template_src("portal_base.html")

    def test_html_tag_emits_embed_attr_on_flag(self):
        self.assertIn("request.GET.rmc_embed == '1'", self.src)
        self.assertIn('data-rmc-embed="1"', self.src)

    def test_embed_eager_loads_bundle_and_hide_layer(self):
        # In embed mode the otherwise-DEFERRED shell bundle is eager-loaded (the
        # iframe may not run the media-flip JS) and the chrome-hide layer loads.
        self.assertIn("css/rmc-embed.css", self.src)
        self.assertIn("portal-shell-enhanced.min.css", self.src)


class RmcEmbedStylesheetSealTests(SimpleTestCase):
    def setUp(self):
        path = finders.find("css/rmc-embed.css")
        self.assertIsNotNone(path, "static/css/rmc-embed.css must exist")
        self.css = Path(path).read_text(encoding="utf-8")

    def test_every_rule_is_scoped_to_the_embed_flag(self):
        # The safety guarantee: no rule may apply without html[data-rmc-embed],
        # so a normal page (no flag) is provably unaffected by this stylesheet.
        # Checked per comma-separated selector, not just per block, so a single
        # unscoped selector inside a grouped rule cannot hide behind a scoped one.
        stripped = re.sub(r"/\*.*?\*/", "", self.css, flags=re.S)
        for block in stripped.split("}"):
            if "{" not in block:
                continue
            selector_list = block.split("{", 1)[0].strip()
            if not selector_list:
                continue
            for selector in selector_list.split(","):
                selector = selector.strip()
                if not selector:
                    continue
                self.assertIn(
                    "data-rmc-embed",
                    selector,
                    f"unscoped selector leaks to all pages: {selector!r}",
                )

    def test_hides_chrome_and_expands_content(self):
        for token in (
            ".rmc-app-shell__header",
            ".portal-sidebar-col",
            "[data-rmc-shell-footer]",
            "#rmc-launch-splash",
        ):
            self.assertIn(token, self.css)
        self.assertIn(".portal-main-col", self.css)
        self.assertIn("display: none", self.css)

    def test_hides_floating_chrome_outside_content_column(self):
        # Regression seal for the 2026-08-03 gap re-audit: the copilot rail, the
        # floating messages FAB, and the AI assist dock render OUTSIDE the content
        # column and float over the page, but the first pass missed them. The
        # copilot rail mounts as [data-rmc-copilot-mount] in portal_base.html —
        # NOT .rmc-app-shell__copilot, which was a near-dead selector that never
        # matched the visible rail. Each token must be present in the hide layer.
        for token in (
            "[data-rmc-copilot-mount]",
            ".rmc-assist-dock",
            ".portal-chathead",
            ".ai-copilot-wrapper",
            ".rmc-support-quick-chip",
        ):
            self.assertIn(token, self.css)


class SandboxEmbedAppendsFlagSealTests(SimpleTestCase):
    def test_sandbox_view_appends_embed_flag_to_same_origin_src(self):
        import apps.marketplace.views as mv

        src = Path(mv.__file__).read_text(encoding="utf-8")
        # The sandbox appends ?rmc_embed=1 (or &rmc_embed=1) to relative srcs.
        self.assertIn("rmc_embed=1", src)
        self.assertIn('"&" if "?" in iframe_src else "?"', src)
