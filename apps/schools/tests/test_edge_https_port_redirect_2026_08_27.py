"""The HTTPS redirect on the web port pointed at a socket that speaks no TLS.

Measured on the Gilead box while somebody was trying to log in:

    http://10.10.20.137:10000/authentication/login/
      -> 301 https://10.10.20.137:10000/authentication/login/   ERR_TIMED_OUT

Nothing terminates TLS on 10000 -- the terminator is on EDGE_TLS_HTTPS_PORT -- so
the browser opened a TLS connection to a plain-HTTP socket and waited. Port 80 was
correct throughout, because Caddy writes that redirect and Django writes this one.

The port cannot simply be closed: `:10000/edge/trust/` is the enrolment URL four
surfaces print, and a device meets the box there before it trusts anything.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.middleware.security import SecurityMiddleware
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.schools.middleware_edge_https_port import (
    EdgeHttpsPortRedirectMiddleware,
    retarget_location,
)

LOGIN = "/authentication/login/"
BOX = "10.10.20.137"


class TheDeadRedirectIsRealTests(SimpleTestCase):
    """Pin what Django actually does, so this cannot quietly stop being the bug."""

    def _security(self, response=None):
        return SecurityMiddleware(lambda r: response or HttpResponse())

    @override_settings(SECURE_SSL_REDIRECT=True, ALLOWED_HOSTS=["*"])
    def test_django_sends_the_browser_to_https_on_the_web_port(self):
        request = RequestFactory().get(LOGIN, HTTP_HOST="%s:10000" % BOX)
        response = self._security().process_request(request)
        self.assertIsNotNone(response, "the premise is that a redirect happens")
        # The port rides along in request.get_host(), and that is the whole defect.
        self.assertEqual(
            response["Location"], "https://%s:10000%s" % (BOX, LOGIN)
        )

    @override_settings(SECURE_SSL_REDIRECT=True, ALLOWED_HOSTS=["*"])
    def test_the_trust_page_is_never_redirected_at_all(self):
        # Load-bearing: a device opens this BECAUSE it does not trust the box yet.
        # If this ever starts redirecting, enrolment shows the warning it came to fix.
        request = RequestFactory().get("/edge/trust/", HTTP_HOST="%s:10000" % BOX)
        self.assertIsNone(self._security().process_request(request))

    @override_settings(SECURE_SSL_REDIRECT=True, ALLOWED_HOSTS=["*"])
    def test_the_health_probe_is_never_redirected_either(self):
        request = RequestFactory().get("/health/", HTTP_HOST="%s:10000" % BOX)
        self.assertIsNone(self._security().process_request(request))


class TheRetargetTests(SimpleTestCase):
    """Only https-on-the-web-port is touched. Everything else passes through."""

    def test_the_live_failure_is_corrected(self):
        self.assertEqual(
            retarget_location("https://%s:10000%s" % (BOX, LOGIN)),
            "https://%s%s" % (BOX, LOGIN),
        )

    def test_a_hostname_is_handled_like_an_address(self):
        self.assertEqual(
            retarget_location("https://gilead-tech.local:10000/dashboard/"),
            "https://gilead-tech.local/dashboard/",
        )

    def test_the_query_string_and_fragment_survive(self):
        self.assertEqual(
            retarget_location("https://%s:10000/x/?next=/y/&a=b" % BOX),
            "https://%s/x/?next=/y/&a=b" % BOX,
        )

    def test_a_url_already_on_the_tls_port_is_untouched(self):
        for url in ("https://%s/x/" % BOX, "https://%s:443/x/" % BOX):
            self.assertEqual(retarget_location(url), url)

    def test_a_plain_http_redirect_is_untouched(self):
        # Django appends slashes and logs people out over http in dev; not ours.
        url = "http://%s:10000/x/" % BOX
        self.assertEqual(retarget_location(url), url)

    def test_a_relative_redirect_is_untouched(self):
        self.assertEqual(retarget_location("/accounts/login/"), "/accounts/login/")

    def test_some_other_port_is_untouched(self):
        # A reverse proxy, a second app, somebody's tunnel. Not this box's web port.
        url = "https://%s:8080/x/" % BOX
        self.assertEqual(retarget_location(url), url)

    def test_a_malformed_authority_is_returned_rather_than_raised(self):
        url = "https://%s:notaport/x/" % BOX
        self.assertEqual(retarget_location(url), url)

    @override_settings()
    def test_a_non_default_tls_port_is_carried_through(self):
        import os

        os.environ["EDGE_TLS_HTTPS_PORT"] = "8443"
        try:
            self.assertEqual(
                retarget_location("https://%s:10000%s" % (BOX, LOGIN)),
                "https://%s:8443%s" % (BOX, LOGIN),
            )
        finally:
            os.environ.pop("EDGE_TLS_HTTPS_PORT", None)

    def test_a_non_default_web_port_is_what_gets_matched(self):
        import os

        os.environ["WEB_PORT"] = "9000"
        try:
            self.assertEqual(
                retarget_location("https://%s:9000/x/" % BOX), "https://%s/x/" % BOX
            )
            # and 10000 is no longer special on such a box
            self.assertEqual(
                retarget_location("https://%s:10000/x/" % BOX),
                "https://%s:10000/x/" % BOX,
            )
        finally:
            os.environ.pop("WEB_PORT", None)

    def test_an_ipv6_literal_keeps_its_brackets(self):
        # urlsplit strips them, and a URL without them is not parseable as a host.
        self.assertEqual(
            retarget_location("https://[fd00::1]:10000/x/"), "https://[fd00::1]/x/"
        )


class TheMiddlewareTests(SimpleTestCase):
    """End to end over the two middlewares, in the order settings declares them."""

    def _through(self, response):
        return EdgeHttpsPortRedirectMiddleware(lambda r: response)(
            RequestFactory().get(LOGIN)
        )

    @override_settings(SECURE_SSL_REDIRECT=True, ALLOWED_HOSTS=["*"])
    def test_it_corrects_what_security_middleware_produced(self):
        request = RequestFactory().get(LOGIN, HTTP_HOST="%s:10000" % BOX)
        bad = SecurityMiddleware(lambda r: HttpResponse()).process_request(request)
        fixed = EdgeHttpsPortRedirectMiddleware(lambda r: bad)(request)
        self.assertEqual(fixed["Location"], "https://%s%s" % (BOX, LOGIN))

    def test_a_normal_response_passes_straight_through(self):
        response = HttpResponse("hello")
        self.assertIs(self._through(response), response)

    def test_a_response_with_no_location_is_not_a_crash(self):
        response = HttpResponse(status=301)
        self.assertEqual(self._through(response).status_code, 301)

    def test_a_permanent_and_a_temporary_redirect_are_both_handled(self):
        for code in (301, 302, 307, 308):
            response = HttpResponse(status=code)
            response["Location"] = "https://%s:10000/x/" % BOX
            self.assertEqual(
                self._through(response)["Location"], "https://%s/x/" % BOX, code
            )

    def test_a_broken_response_object_never_becomes_a_500(self):
        class Hostile:
            status_code = 302

            @property
            def headers(self):
                raise RuntimeError("boom")

        hostile = Hostile()
        self.assertIs(self._through(hostile), hostile)


class TheOrderingIsLoadBearingTests(SimpleTestCase):
    """Listed after SecurityMiddleware, it would never see the redirect."""

    def test_it_is_registered(self):
        from django.conf import settings

        self.assertIn(
            "apps.schools.middleware_edge_https_port.EdgeHttpsPortRedirectMiddleware",
            settings.MIDDLEWARE,
        )

    def test_it_sits_above_security_middleware(self):
        from django.conf import settings

        chain = list(settings.MIDDLEWARE)
        self.assertLess(
            chain.index(
                "apps.schools.middleware_edge_https_port."
                "EdgeHttpsPortRedirectMiddleware"
            ),
            chain.index("django.middleware.security.SecurityMiddleware"),
        )
