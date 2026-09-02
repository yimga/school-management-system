"""Operator (/super/) remote-support CONSOLE page — gating + contract tests (no DB).

The console view is GET-only and does no heavy query (the table hydrates from
sessions.json via JS). Rendering the full control-plane skeleton triggers
context processors that query the DB, so these tests never render it — they
assert the view's render() call + context (mocked render), the template's static
hooks (from source), and the JS<->template integration contract (from source),
all without a database. Control-plane access is enforced by
``require_super_access_with_host`` (tested below); per-tenant scope is enforced
inside the accept/end views (covered by test_super_remote_support.py).
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from apps.schools import super_views_remote_support as srs
from apps.siteconfig.tests._template_nodes import assert_markup, assert_wires

rf = RequestFactory()

_ROOT = Path(srs.__file__).resolve().parents[2]
_TEMPLATE = _ROOT / "templates" / "schools" / "super_remote_support_console.html"
_JS = _ROOT / "static" / "js" / "rmc-super-remote-support.js"
_PLACEHOLDER = "00000000-0000-0000-0000-000000000000"


class _Operator:
    is_authenticated = True
    is_superuser = True
    is_staff = True
    id = 7
    pk = 7


class SuperRemoteSupportConsoleViewTests(SimpleTestCase):
    """The view contract + template/JS integration — all no-DB."""

    def test_view_renders_expected_template_and_context(self):
        captured = {}

        def _fake_render(request, template, context=None, *a, **k):
            captured["template"] = template
            captured["context"] = context or {}
            return HttpResponse(b"ok")

        req = rf.get("/super/remote-support/")
        req.user = _Operator()
        with mock.patch.object(srs, "render", side_effect=_fake_render):
            resp = srs.super_remote_support_console(req)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            captured["template"], "schools/super_remote_support_console.html"
        )
        ctx = captured["context"]
        # reverse() needs no DB; assert the REAL endpoint URLs flow into the page.
        self.assertEqual(ctx["sessions_url"], "/super/remote-support/sessions.json")
        self.assertIn("/accept/", ctx["accept_url_template"])
        self.assertIn("/end/", ctx["end_url_template"])
        # The placeholder UUID the JS swaps per row must be in both action URLs.
        self.assertIn(_PLACEHOLDER, ctx["accept_url_template"])
        self.assertIn(_PLACEHOLDER, ctx["end_url_template"])

    def test_template_source_carries_static_hooks(self):
        src = _TEMPLATE.read_text(encoding="utf-8")
        # A {% static %} argument is never emitted text, so the bundle name is
        # only visible in the source.
        self.assertIn("rmc-super-remote-support.js", src)
        # Carries no inline style attributes -- a negative over the whole source.
        self.assertNotIn("style=", src)
        # Every other hook here is plain markup, and reading the file cannot tell
        # a live console from one whose body sits inside {% comment %} -- which is
        # a page the JS binds nothing to. Ask the engine what is EMITTED.
        assert_markup(
            self,
            _TEMPLATE,
            'id="rmc-super-remote-support-config"',
            "data-rmc-remote-support-rows",
            "data-rmc-remote-support-empty-row",
            "data-rmc-remote-support-refresh",
            "data-rmc-remote-support-status",
            "sessions_url",
            "accept_url_template",
            "end_url_template",
        )
        # Extends the control-plane base. A parse sees the ExtendsNode; a comment
        # produces none, which is what "extends" has to mean here.
        assert_wires(self, _TEMPLATE, "control_plane_base.html")

    def test_js_template_integration_contract(self):
        # The hooks/config keys the JS consumes must be emitted by the template --
        # this is the operator click-path contract (open -> see -> accept/end).
        js = _JS.read_text(encoding="utf-8")

        self.assertIn("rmc-super-remote-support-config", js)
        for key in ("sessions_url", "accept_url_template", "end_url_template"):
            self.assertIn(key, js)
        # Containers the JS queries.
        for hook in ("data-rmc-remote-support-rows", "data-rmc-remote-support-status"):
            self.assertIn(hook, js)
        # The template half of the contract says "emitted by the template", and
        # only a parse can check that. A source read passes over a console whose
        # whole body has been commented out, which is exactly the page on which
        # this integration silently stops existing.
        assert_markup(
            self,
            _TEMPLATE,
            "rmc-super-remote-support-config",
            "sessions_url",
            "accept_url_template",
            "end_url_template",
            "data-rmc-remote-support-rows",
            "data-rmc-remote-support-status",
        )
        # Action hooks the JS generates + listens for (template need not contain them).
        for hook in (
            "data-rmc-remote-support-accept",
            "data-rmc-remote-support-end",
            "data-rmc-remote-support-refresh",
        ):
            self.assertIn(hook, js)
        # CSRF regression guard: the manager-host cookie name MUST be read (the
        # /super/ host blanks the plain csrftoken cookie -- without this the
        # Accept/End POSTs ship an empty token and Django 403s them).
        self.assertIn("rmc_manager_csrftoken", js)


class SuperRemoteSupportConsoleAccessTests(SimpleTestCase):
    """The /super/ route resolves and the access wrapper denies non-operators."""

    def test_route_resolves_to_expected_path(self):
        from django.urls import reverse

        url = reverse("super:remote_support_console", urlconf="config.manager_urls")
        self.assertEqual(url, "/super/remote-support/")

    def test_sessions_json_route_still_resolves_distinctly(self):
        # The page mount "remote-support/" must NOT shadow "remote-support/sessions.json".
        from django.urls import resolve, reverse

        page = reverse("super:remote_support_console", urlconf="config.manager_urls")
        sessions = reverse(
            "super:remote_support_sessions", urlconf="config.manager_urls"
        )
        self.assertEqual(page, "/super/remote-support/")
        self.assertEqual(sessions, "/super/remote-support/sessions.json")
        match = resolve(
            "/super/remote-support/sessions.json", urlconf="config.manager_urls"
        )
        self.assertEqual(match.url_name, "remote_support_sessions")

    def test_wrapper_denies_non_operator_with_403(self):
        # The require_super_access_with_host gate must short-circuit a non-operator
        # (authenticated but without control-plane access) BEFORE the view renders.
        from apps.schools.control_plane import require_super_access_with_host

        wrapped = require_super_access_with_host(srs.super_remote_support_console)
        req = rf.get("/super/remote-support/")

        class _NonOperator:
            is_authenticated = True
            is_superuser = False
            is_staff = False
            id = 9
            pk = 9

        req.user = _NonOperator()
        with mock.patch(
            "apps.schools.control_plane._is_super_surface", return_value=True
        ), mock.patch(
            "apps.schools.control_plane.user_has_control_plane_access",
            return_value=False,
        ):
            resp = wrapped(req)
        self.assertEqual(resp.status_code, 403)
