"""Tests for the Content-Security-Policy middleware + report endpoint."""

from __future__ import annotations

import json

from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.security.csp_middleware import (
    _DEFAULT_DIRECTIVES,
    ContentSecurityPolicyMiddleware,
    _build_admin_policy,
    _build_policy,
    admin_default_directives,
    csp_nonce,
)


def _directive(policy: str, name: str) -> str:
    """Return the single ``name ...`` directive out of a policy string.

    Raises StopIteration if absent — an absent directive is a test failure, not
    a silently-empty string to assert against.
    """
    return next(p for p in policy.split("; ") if p.startswith(name + " "))


def _get_response(request):
    return HttpResponse("<html>ok</html>", content_type="text/html")


class CspMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(CSP_ENFORCE=True)
    def test_html_response_gets_csp_enforce_header_by_default(self):
        """CSP_ENFORCE defaults True; strict script-src + unsafe-inline style-src."""
        mw = ContentSecurityPolicyMiddleware(_get_response)
        resp = mw(self.factory.get("/"))
        self.assertIn("Content-Security-Policy", resp)
        self.assertNotIn("Content-Security-Policy-Report-Only", resp)
        self.assertIn("default-src 'self'", resp["Content-Security-Policy"])

    @override_settings(CSP_ENFORCE=False)
    def test_html_response_gets_report_only_when_enforce_disabled(self):
        mw = ContentSecurityPolicyMiddleware(_get_response)
        resp = mw(self.factory.get("/"))
        self.assertIn("Content-Security-Policy-Report-Only", resp)
        self.assertNotIn("Content-Security-Policy", resp)
        self.assertIn("default-src 'self'", resp["Content-Security-Policy-Report-Only"])

    def test_admin_is_no_longer_bypassed(self):
        """/admin/ used to receive NO CSP header at all (it sat in
        BYPASS_PREFIXES). It must now receive a policy — Report-Only."""
        mw = ContentSecurityPolicyMiddleware(_get_response)
        resp = mw(self.factory.get("/admin/login/"))
        self.assertIn("Content-Security-Policy-Report-Only", resp)

    @override_settings(CSP_ENFORCE=True)
    def test_admin_index_root_is_covered(self):
        # Regression on the prefix matcher: the bare admin index "/admin/" must
        # be recognised as the admin surface, not just "/admin/<app>/...". An
        # earlier rstrip('/').startswith('/admin/') form failed for the exact
        # root ("/admin/" -> "/admin", not a prefix-match).
        mw = ContentSecurityPolicyMiddleware(_get_response)
        for path in ("/admin/", "/admin"):
            resp = mw(self.factory.get(path))
            self.assertIn("Content-Security-Policy-Report-Only", resp, path)
            self.assertNotIn("Content-Security-Policy", resp, path)

    @override_settings(CSP_ENFORCE=True)
    def test_non_admin_lookalike_not_bypassed(self):
        # "/administrators/" must NOT be treated as under "/admin/".
        mw = ContentSecurityPolicyMiddleware(_get_response)
        resp = mw(self.factory.get("/administrators/"))
        self.assertIn("Content-Security-Policy", resp)

    @override_settings(CSP_ENFORCE=True)
    def test_static_path_bypassed(self):
        mw = ContentSecurityPolicyMiddleware(_get_response)
        resp = mw(self.factory.get("/static/css/x.css"))
        self.assertNotIn("Content-Security-Policy-Report-Only", resp)

    def test_non_html_response_not_decorated(self):
        def json_response(request):
            return HttpResponse('{"ok": true}', content_type="application/json")

        mw = ContentSecurityPolicyMiddleware(json_response)
        resp = mw(self.factory.get("/api/x"))
        self.assertNotIn("Content-Security-Policy-Report-Only", resp)

    @override_settings(
        CSP_EXTRA_SCRIPT_SRC=("https://cdn.example.com",),
        CSP_REPORT_URI="/security/csp-report/",
    )
    def test_extra_origins_appear_in_policy(self):
        policy = _build_policy()
        self.assertIn("https://cdn.example.com", policy)
        self.assertIn("report-uri /security/csp-report/", policy)

    def test_default_policy_is_self_only(self):
        policy = _build_policy()
        self.assertIn("default-src 'self'", policy)
        self.assertIn("script-src 'self'", policy)
        self.assertIn("frame-ancestors 'self'", policy)
        self.assertIn("object-src 'none'", policy)

    def test_nonce_appears_in_script_src_when_provided(self):
        policy = _build_policy(nonce="abc123")
        self.assertIn("script-src 'self' 'nonce-abc123'", policy)

    def test_script_src_is_strict_no_unsafe(self):
        """script-src is the XSS-critical directive: 'self' + nonce, never
        'unsafe-inline'/'unsafe-eval'."""
        policy = _build_policy(nonce="abc123")
        # Isolate the script-src directive and assert no unsafe tokens in it.
        script_src = next(
            p for p in policy.split("; ") if p.startswith("script-src ")
        )
        self.assertNotIn("'unsafe-inline'", script_src)
        self.assertNotIn("'unsafe-eval'", script_src)

    def test_style_src_uses_unsafe_inline_and_no_nonce(self):
        """Path A: style-src carries 'unsafe-inline' (inline style ATTRIBUTES cannot
        be nonced), and the nonce must NOT be added to style-src — a directive with
        BOTH a nonce and 'unsafe-inline' makes browsers IGNORE 'unsafe-inline' (CSP3),
        which would re-break every inline style attribute."""
        policy = _build_policy(nonce="abc123")
        style_src = next(
            p for p in policy.split("; ") if p.startswith("style-src ")
        )
        self.assertIn("'unsafe-inline'", style_src)
        self.assertNotIn("nonce-", style_src)

    @override_settings(CSP_ENFORCE=True)
    def test_middleware_sets_request_nonce_and_header_token(self):
        mw = ContentSecurityPolicyMiddleware(_get_response)
        request = self.factory.get("/super/")
        mw(request)
        self.assertTrue(getattr(request, "csp_nonce", ""))
        ctx = csp_nonce(request)
        self.assertEqual(ctx["csp_nonce"], request.csp_nonce)


class CspAdminSurfaceTests(SimpleTestCase):
    """/admin/ is under CSP in Report-Only mode.

    The admin was the ONLY surface with no CSP header at all, which made it the
    one place a script-injection had zero policy in its way. It now carries its
    own, deliberately looser policy so operators can LEARN the real violation
    set before deciding anything about enforcement.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.mw = ContentSecurityPolicyMiddleware(_get_response)

    # -- mode ---------------------------------------------------------------

    @override_settings(CSP_ENFORCE=True)
    def test_admin_gets_report_only_never_enforcing_by_default(self):
        """The site switch is ON here; the admin must still be Report-Only.

        CSP_ENFORCE promoting the admin as a side effect is the exact accident
        this rollout must not ship.
        """
        for path in ("/admin/", "/admin", "/admin/login/", "/admin/auth/user/1/change/"):
            resp = self.mw(self.factory.get(path))
            self.assertIn("Content-Security-Policy-Report-Only", resp, path)
            self.assertNotIn("Content-Security-Policy", resp, path)

    @override_settings(CSP_ENFORCE=False)
    def test_admin_report_only_when_site_is_report_only_too(self):
        resp = self.mw(self.factory.get("/admin/"))
        self.assertIn("Content-Security-Policy-Report-Only", resp)
        self.assertNotIn("Content-Security-Policy", resp)

    @override_settings(CSP_ENFORCE=False, CSP_ADMIN_ENFORCE=True)
    def test_admin_enforcing_requires_explicit_opt_in(self):
        """CSP_ADMIN_ENFORCE is the ONLY way to enforce on /admin/."""
        resp = self.mw(self.factory.get("/admin/"))
        self.assertIn("Content-Security-Policy", resp)
        self.assertNotIn("Content-Security-Policy-Report-Only", resp)

    def test_admin_enforce_default_is_off_in_settings(self):
        """The shipped default must be off — not merely off in this test env."""
        from django.conf import settings as live_settings

        self.assertFalse(getattr(live_settings, "CSP_ADMIN_ENFORCE", False))

    @override_settings(CSP_ADMIN_ENABLED=False, CSP_ENFORCE=True)
    def test_admin_header_can_be_disabled_entirely(self):
        """Escape hatch: restore the pre-rollout no-header behaviour."""
        resp = self.mw(self.factory.get("/admin/"))
        self.assertNotIn("Content-Security-Policy", resp)
        self.assertNotIn("Content-Security-Policy-Report-Only", resp)

    def test_non_html_admin_response_not_decorated(self):
        def json_response(request):
            return HttpResponse('{"ok": true}', content_type="application/json")

        mw = ContentSecurityPolicyMiddleware(json_response)
        resp = mw(self.factory.get("/admin/jsi18n/"))
        self.assertNotIn("Content-Security-Policy-Report-Only", resp)
        self.assertNotIn("Content-Security-Policy", resp)

    # -- the policy actually fits the admin ---------------------------------

    def test_admin_policy_carries_unsafe_eval_for_alpine(self):
        """Unfold bundles the STANDARD Alpine build, whose evaluator is
        ``Object.getPrototypeOf(async function(){}).constructor`` (the
        AsyncFunction constructor) — eval-equivalent. Without 'unsafe-eval'
        every Alpine directive in the admin dies the moment this is enforced."""
        script_src = _directive(_build_admin_policy(), "script-src")
        self.assertIn("'unsafe-eval'", script_src)

    def test_admin_policy_carries_unsafe_inline_for_inline_handlers(self):
        """templates/admin/ still carries onclick= style attributes, which a
        nonce cannot authorize."""
        script_src = _directive(_build_admin_policy(), "script-src")
        self.assertIn("'unsafe-inline'", script_src)

    def test_admin_script_src_has_no_nonce_beside_unsafe_inline(self):
        """CSP3 trap: a directive carrying BOTH a nonce and 'unsafe-inline'
        makes browsers IGNORE 'unsafe-inline'. Shipping both would mean the
        admin policy passes review while still breaking every inline handler
        the instant someone flips CSP_ADMIN_ENFORCE."""
        script_src = _directive(_build_admin_policy(), "script-src")
        self.assertIn("'unsafe-inline'", script_src)
        self.assertNotIn("nonce-", script_src)

    def test_admin_response_header_carries_no_nonce(self):
        """Same assertion end-to-end, not just on the builder."""
        resp = self.mw(self.factory.get("/admin/"))
        script_src = _directive(
            resp["Content-Security-Policy-Report-Only"], "script-src"
        )
        self.assertNotIn("nonce-", script_src)

    def test_admin_policy_allows_the_google_fonts_stylesheet(self):
        """admin/base_site.html links fonts.googleapis.com; the site policy's
        style-src ('self' + 'unsafe-inline') would block it."""
        style_src = _directive(_build_admin_policy(), "style-src")
        self.assertIn("https://fonts.googleapis.com", style_src)
        self.assertIn("'unsafe-inline'", style_src)

    def test_admin_policy_keeps_load_bearing_directives(self):
        """Looser on script/style does not mean loose everywhere."""
        policy = _build_admin_policy()
        self.assertIn("object-src 'none'", policy)
        self.assertIn("frame-ancestors 'self'", policy)
        self.assertIn("base-uri 'self'", policy)
        self.assertIn("form-action 'self'", policy)
        self.assertIn("default-src 'self'", policy)

    def test_admin_policy_inherits_every_base_directive_token(self):
        """The admin baseline is a DELTA over _DEFAULT_DIRECTIVES, not a
        parallel table — so future hardening of the base policy propagates
        instead of silently drifting (the bug csp_readiness.py already hit)."""
        admin = admin_default_directives()
        for directive, sources in _DEFAULT_DIRECTIVES.items():
            self.assertIn(directive, admin)
            for token in sources:
                self.assertIn(token, admin[directive], f"{directive}/{token}")

    # -- reporting ----------------------------------------------------------

    @override_settings(CSP_REPORT_URI="/security/csp-report/")
    def test_admin_policy_reports_to_the_site_sink_by_default(self):
        """Report-Only with nowhere to send reports learns nothing."""
        self.assertIn("report-uri /security/csp-report/", _build_admin_policy())

    @override_settings(
        CSP_REPORT_URI="/security/csp-report/",
        CSP_ADMIN_REPORT_URI="/security/csp-report/?surface=admin",
    )
    def test_admin_report_uri_override_wins(self):
        self.assertIn(
            "report-uri /security/csp-report/?surface=admin",
            _build_admin_policy(),
        )

    # -- configurability ----------------------------------------------------

    @override_settings(
        CSP_ADMIN_EXTRA_SCRIPT_SRC=("https://cdn.admin.example",),
        CSP_ADMIN_EXTRA_STYLE_SRC=("https://css.admin.example",),
        CSP_ADMIN_EXTRA_FONT_SRC=("https://font.admin.example",),
        CSP_ADMIN_EXTRA_FRAME_SRC=("https://frame.admin.example",),
    )
    def test_admin_extra_origins_are_settings_driven(self):
        policy = _build_admin_policy()
        self.assertIn("https://cdn.admin.example", _directive(policy, "script-src"))
        self.assertIn("https://css.admin.example", _directive(policy, "style-src"))
        self.assertIn("https://font.admin.example", _directive(policy, "font-src"))
        # frame-src is absent from the base table; the extras must create it.
        self.assertIn("https://frame.admin.example", _directive(policy, "frame-src"))

    @override_settings(CSP_ADMIN_EXTRA_SCRIPT_SRC=("https://cdn.admin.example",))
    def test_admin_extras_do_not_leak_into_the_site_policy(self):
        self.assertNotIn("https://cdn.admin.example", _build_policy())

    @override_settings(CSP_ADMIN_PATH_PREFIXES=("/backoffice/",), CSP_ENFORCE=True)
    def test_admin_prefixes_are_settings_driven(self):
        resp = self.mw(self.factory.get("/backoffice/dashboard/"))
        self.assertIn("Content-Security-Policy-Report-Only", resp)
        self.assertIn(
            "'unsafe-eval'",
            _directive(resp["Content-Security-Policy-Report-Only"], "script-src"),
        )
        # /admin/ is no longer the admin surface under this override, so it
        # falls through to the site policy (enforcing here).
        resp_admin = self.mw(self.factory.get("/admin/"))
        self.assertIn("Content-Security-Policy", resp_admin)
        self.assertNotIn(
            "'unsafe-eval'", _directive(resp_admin["Content-Security-Policy"], "script-src")
        )

    @override_settings(CSP_ADMIN_PATH_PREFIXES=(), CSP_ENFORCE=True)
    def test_empty_prefix_override_falls_back_instead_of_failing_open(self):
        """An empty prefix list must NOT mean "no admin surface".

        Honouring it would drop /admin/ through to the site policy — which can
        be ENFORCING — and break the admin outright. CSP_ADMIN_ENABLED is the
        opt-out; this knob only relocates the surface.
        """
        resp = self.mw(self.factory.get("/admin/"))
        self.assertIn("Content-Security-Policy-Report-Only", resp)
        self.assertNotIn("Content-Security-Policy", resp)

    # -- bypasses -----------------------------------------------------------

    @override_settings(CSP_ENFORCE=True)
    def test_static_and_media_still_bypassed(self):
        """Asset bytes, not HTML documents — still no header of either kind."""
        for path in ("/static/css/x.css", "/static/", "/media/uploads/a.png", "/media/"):
            resp = self.mw(self.factory.get(path))
            self.assertNotIn("Content-Security-Policy", resp, path)
            self.assertNotIn("Content-Security-Policy-Report-Only", resp, path)

    def test_static_and_media_are_the_only_bypasses(self):
        self.assertEqual(
            set(ContentSecurityPolicyMiddleware.BYPASS_PREFIXES),
            {"/static/", "/media/"},
        )
        self.assertNotIn("/admin/", ContentSecurityPolicyMiddleware.BYPASS_PREFIXES)


class CspSiteRegressionTests(SimpleTestCase):
    """The admin rollout must not change the non-admin site by one byte.

    This is the regression risk of the change: a new branch in ``__call__``
    that accidentally catches site paths, or admin tokens bleeding into the
    site policy, would silently loosen every tenant page.
    """

    SITE_PATHS = (
        "/",
        "/super/",
        "/administrators/",       # /admin/ lookalike — must NOT be the admin surface
        "/adminfoo",
        "/portal/dashboard/",
        "/staticfiles/x",         # /static/ lookalike — must NOT be bypassed
        "/mediakit/",             # /media/ lookalike — must NOT be bypassed
        "/security/csp-report/",
    )

    def setUp(self):
        self.factory = RequestFactory()
        self.mw = ContentSecurityPolicyMiddleware(_get_response)

    @override_settings(CSP_ENFORCE=True)
    def test_site_paths_still_get_the_enforcing_site_policy(self):
        for path in self.SITE_PATHS:
            request = self.factory.get(path)
            resp = self.mw(request)
            self.assertIn("Content-Security-Policy", resp, path)
            self.assertNotIn("Content-Security-Policy-Report-Only", resp, path)
            # Byte-exact: the header equals what _build_policy produces for
            # this request's nonce — i.e. the admin branch never touched it.
            self.assertEqual(
                resp["Content-Security-Policy"],
                _build_policy(nonce=request.csp_nonce),
                path,
            )

    @override_settings(CSP_ENFORCE=False)
    def test_site_paths_still_get_report_only_when_disabled(self):
        for path in self.SITE_PATHS:
            request = self.factory.get(path)
            resp = self.mw(request)
            self.assertIn("Content-Security-Policy-Report-Only", resp, path)
            self.assertNotIn("Content-Security-Policy", resp, path)
            self.assertEqual(
                resp["Content-Security-Policy-Report-Only"],
                _build_policy(nonce=request.csp_nonce),
                path,
            )

    @override_settings(CSP_ENFORCE=True)
    def test_site_policy_never_carries_the_admin_relaxations(self):
        """The whole point of a SEPARATE admin policy: 'unsafe-eval' and the
        script-src 'unsafe-inline' must stay off the site surface."""
        for path in self.SITE_PATHS:
            resp = self.mw(self.factory.get(path))
            script_src = _directive(resp["Content-Security-Policy"], "script-src")
            self.assertNotIn("'unsafe-eval'", script_src, path)
            self.assertNotIn("'unsafe-inline'", script_src, path)

    @override_settings(CSP_ENFORCE=True)
    def test_site_paths_still_receive_the_per_request_nonce(self):
        for path in self.SITE_PATHS:
            request = self.factory.get(path)
            resp = self.mw(request)
            self.assertTrue(getattr(request, "csp_nonce", ""), path)
            self.assertIn(
                f"'nonce-{request.csp_nonce}'",
                _directive(resp["Content-Security-Policy"], "script-src"),
                path,
            )

    def test_admin_paths_still_get_a_request_nonce_for_templates(self):
        """base_site.html renders nonce="{{ csp_nonce }}"; the attribute must
        still resolve even though the admin policy does not use a nonce."""
        request = self.factory.get("/admin/")
        self.mw(request)
        self.assertTrue(getattr(request, "csp_nonce", ""))
        self.assertEqual(csp_nonce(request)["csp_nonce"], request.csp_nonce)


class CspReportEndpointTests(TestCase):
    def test_valid_legacy_report_returns_204(self):
        body = json.dumps({
            "csp-report": {
                "violated-directive": "script-src",
                "blocked-uri": "inline",
                "document-uri": "https://example.test/page",
            }
        }).encode("utf-8")
        url = reverse("csp_violation_report")
        resp = self.client.post(url, data=body, content_type="application/json")
        self.assertEqual(resp.status_code, 204)

    def test_modern_reporting_api_payload_returns_204(self):
        body = json.dumps({
            "violated-directive": "img-src",
            "blocked-uri": "https://tracker.example/x.gif",
        }).encode("utf-8")
        url = reverse("csp_violation_report")
        resp = self.client.post(url, data=body, content_type="application/json")
        self.assertEqual(resp.status_code, 204)

    def test_invalid_json_returns_400(self):
        url = reverse("csp_violation_report")
        resp = self.client.post(url, data=b"not-json", content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_get_method_not_allowed(self):
        url = reverse("csp_violation_report")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 405)


@override_settings(ALLOWED_HOSTS=["*"])
class CspAdminEndToEndTests(TestCase):
    """A REAL request, through the REAL middleware stack, to a REAL admin page.

    Every other class in this file drives the middleware directly with a
    RequestFactory. That proves the policy BUILDER is correct and proves
    nothing about whether a browser ever receives the header -- a middleware
    that is never reached emits nothing while its unit tests stay green.

    WHY testserver AND NOT manager.runmycampus.com
    ----------------------------------------------
    Measured 2026-09-06, anonymous, against the full stack:

        testserver/admin/login/                 200  admin Report-Only policy
        manager.runmycampus.com/admin/login/    302  NO CSP header at all
        manager.runmycampus.com/admin/          302  NO CSP header at all
        gilead-school.../admin/login/           202  NO CSP header at all
        manager.runmycampus.com/authentication/login/
                                                302  site policy, enforcing

    The manager and tenant results are NOT this middleware failing. Those
    responses are produced by middleware that short-circuits UPSTREAM of it:
    ContentSecurityPolicyMiddleware is index 83 of 88, and
    ManagerHostControlPlaneRequiredMiddleware (index 52) redirects /admin/ to
    /super/ long before the request gets there. A response returned by an
    earlier middleware never traverses a later one, so it carries no CSP --
    which is a property of the ORDERING, platform-wide and pre-existing, not
    of the bypass removal this file tests.

    The middleware keys off ``request.path`` alone, so the host does not change
    the decision; testserver is used because it is the surface where an admin
    page actually RENDERS anonymously and there is therefore a header to assert
    on. Asserting against a 302 would pass vacuously and prove nothing.
    """

    ENFORCE = "Content-Security-Policy"
    REPORT_ONLY = "Content-Security-Policy-Report-Only"

    def _rendered_admin_page(self):
        """An admin response that is genuinely an HTML document, or fail loudly."""
        resp = Client().get("/admin/login/")
        self.assertEqual(
            resp.status_code,
            200,
            "/admin/login/ must RENDER for this class to mean anything; got "
            f"{resp.status_code}. A redirect carries no document and every "
            "assertion below would pass vacuously.",
        )
        self.assertTrue(
            (resp.headers.get("Content-Type") or "").startswith("text/html"),
            "the middleware stamps HTML only, so a non-HTML body here would "
            "make the assertions below meaningless",
        )
        return resp

    def test_admin_surface_actually_receives_a_header(self):
        """The regression this change exists to close.

        Before it, ``/admin/`` sat in BYPASS_PREFIXES and the highest-privilege
        surface on the platform was the ONLY one with no CSP telemetry at all.
        """
        resp = self._rendered_admin_page()
        self.assertIn(
            self.REPORT_ONLY,
            resp.headers,
            "a rendered admin page received NO CSP header -- this is exactly "
            "the bypass that was removed; check BYPASS_PREFIXES and that "
            "ContentSecurityPolicyMiddleware is still installed",
        )

    def test_admin_surface_is_report_only_not_enforcing(self):
        """CSP_ADMIN_ENFORCE defaults False and CSP_ENFORCE must not override it.

        The deployed services run CSP_ENFORCE=1. Were the admin policy wired to
        that flag it would go enforcing on the next deploy and take every Alpine
        directive in the admin with it.
        """
        resp = self._rendered_admin_page()
        self.assertNotIn(
            self.ENFORCE,
            resp.headers,
            "the admin surface is ENFORCING; CSP_ADMIN_ENFORCE defaults to "
            "False and must stay a separate, explicit opt-in",
        )

    def test_admin_gets_the_admin_policy_not_the_site_policy(self):
        """Prefix routing must discriminate at RUNTIME, not just in a unit test."""
        policy = self._rendered_admin_page().headers[self.REPORT_ONLY]
        self.assertIn(
            "'unsafe-eval'",
            _directive(policy, "script-src"),
            "the SITE policy was served on /admin/: Unfold bundles the standard "
            "Alpine build, whose evaluator is the AsyncFunction constructor, so "
            "every admin directive would break the moment this went enforcing",
        )
        self.assertIn(
            "https://fonts.googleapis.com",
            _directive(policy, "style-src"),
            "admin/base_site.html links a Google Fonts stylesheet",
        )

    def test_non_admin_page_is_not_widened_by_the_admin_additions(self):
        """The admin loosenings must not leak onto an ordinary page.

        Asserted over the wire on a real non-admin URL, so this is the runtime
        half of the discrimination claim rather than a second builder test.
        """
        resp = Client(HTTP_HOST="manager.runmycampus.com").get("/authentication/login/")
        policy = (
            resp.headers.get(self.ENFORCE)
            or resp.headers.get(self.REPORT_ONLY)
            or ""
        )
        self.assertTrue(
            policy,
            "a non-admin page carried no CSP header at all, so this test cannot "
            "show the admin additions were withheld from it",
        )
        self.assertNotIn(
            "'unsafe-eval'",
            _directive(policy, "script-src"),
            "the ADMIN policy leaked onto a non-admin page -- check _is_admin "
            "and CSP_ADMIN_PATH_PREFIXES",
        )
