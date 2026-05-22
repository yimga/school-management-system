"""Phase 12 (Wave F) — Django test-client render smoke for the auto-chrome partial.

Runs in CI without a browser, without auth, without ``E2E_LOGIN_USER``. Uses
Django's test ``Client`` to GET anonymous-reachable pages and asserts:

  * No template-syntax leaks in rendered HTML (no ``{% include %}`` literal,
    no ``{{ wf.* }}`` literal, no ``[object Object]``).
  * No ``data-rmc-workflow-key=""`` (empty key would indicate the auto-chrome
    rendered without a resolved workflow — a regression in the empty-state
    guard).
  * ``rmc-workflow-guidance.css`` is reachable at the static path the auto-
    chrome partial references.

Anonymous pages chosen so the test runs without database fixtures.
"""
from __future__ import annotations

import re

from django.test import Client, SimpleTestCase


TEMPLATE_SYNTAX_LEAK_PATTERNS = (
    re.compile(r"\{\%\s*(include|workflow_resolve|if|for|with)\b"),
    re.compile(r"\{\{\s*rmc_wf_auto"),
    re.compile(r"\{\{\s*wf\."),
)


class AutoChromeAnonymousRenderTests(SimpleTestCase):
    """Anonymous GETs on a few platform surfaces — assert no template leaks
    and no empty workflow-chrome wrappers."""

    def setUp(self):
        self.client = Client()

    def _assert_no_template_leak(self, body: str, url: str):
        for pattern in TEMPLATE_SYNTAX_LEAK_PATTERNS:
            self.assertIsNone(
                pattern.search(body),
                f"Template syntax leak on {url}: matched {pattern.pattern!r}",
            )
        self.assertNotIn("[object Object]", body, f"JS-stringify leak on {url}")

    def _assert_no_empty_workflow_key(self, body: str, url: str):
        # The auto-chrome partial only emits ``data-rmc-workflow-key="..."``
        # with a non-empty value when a workflow resolved. An empty value would
        # mean the guard broke.
        empty_key = re.search(r'data-rmc-workflow-key=""', body)
        self.assertIsNone(
            empty_key,
            f"Empty workflow-key attribute on {url} — auto-chrome guard regression",
        )

    def test_static_css_bundle_referenced_by_partial_is_under_static_dir(self):
        """The auto-chrome partial assumes the bundle is at
        ``static/css/rmc-workflow-guidance.css``. Confirm the file exists at
        that path on disk."""
        import pathlib
        p = pathlib.Path(__file__).resolve().parents[3] / "static" / "css" / "rmc-workflow-guidance.css"
        self.assertTrue(p.exists(), f"Workflow guidance CSS bundle missing at {p}")

    def test_login_page_has_no_template_leak(self):
        """The login page exists on every host and is anonymous-reachable."""
        # Use a relative URL; resolves through Django's test client which uses
        # the default URLconf (config.urls). The login route name is
        # ``accounts:login`` on the platform; tolerate redirect.
        resp = self.client.get("/accounts/login/", follow=True)
        # 200 or 302-followed-to-200; just don't crash with 500
        self.assertLess(resp.status_code, 500, "Login page returned 5xx — server error")
        body = resp.content.decode("utf-8", errors="ignore")
        self._assert_no_template_leak(body, "/accounts/login/")
        self._assert_no_empty_workflow_key(body, "/accounts/login/")

    def test_anonymous_root_redirects_safely(self):
        """The root path should redirect to login (or render a marketing
        page). Either way: no template leaks."""
        resp = self.client.get("/", follow=True)
        self.assertLess(resp.status_code, 500)
        body = resp.content.decode("utf-8", errors="ignore")
        self._assert_no_template_leak(body, "/")
        self._assert_no_empty_workflow_key(body, "/")


class WorkflowGuidanceTagLibraryLoadsTests(SimpleTestCase):
    """The ``workflow_guidance_tags`` library must load via Django's template
    engine without raising. This is the minimum guarantee that the auto-chrome
    include in shells will not 500."""

    def test_library_resolves(self):
        from django.template import Template, Context
        # Render a minimal template that loads the library and uses one tag.
        t = Template(
            '{% load workflow_guidance_tags %}'
            '{% workflow_resolve "studio-os-output" as wf %}'
            '{% if wf %}OK{% else %}NONE{% endif %}'
        )
        rendered = t.render(Context({}))
        # Either "OK" (workflow seeded + visibility check passes) or "NONE"
        # (no workflow OR not visible) — both are acceptable; the test asserts
        # the library loads + the tag runs without raising.
        self.assertIn(rendered, ("OK", "NONE"))

    def test_workflow_status_payload_filter_handles_none(self):
        from django.template import Template, Context
        t = Template(
            '{% load workflow_guidance_tags %}'
            'X{{ None|workflow_status_payload:None|default:"empty" }}Y'
        )
        # Must not raise even on None input
        rendered = t.render(Context({}))
        self.assertTrue(rendered.startswith("X"))
        self.assertTrue(rendered.endswith("Y"))
