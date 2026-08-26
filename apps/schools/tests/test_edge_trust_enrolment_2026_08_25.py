"""The box publishes its own CA, and a test host never reaches a certificate.

WHAT HAPPENED. Installing a box CA meant copying two files off the box by hand --
VS Code over SSH, or a USB stick -- and then walking ``box-ca.crt`` to every phone,
tablet and laptop in the building. Thirty devices, one file, passed around. One of
those two files is ``box-ca-bundle.p12``, which carries the CA PRIVATE KEY, and the
bootstrap wrote it into ``/srv/rmc`` -- a git working tree, with neither name in
.gitignore. A single ``git add -A`` on that box publishes a certificate authority.

While proving the address list on a real box, ``testserver`` was sitting in it. That
is Django's default ``SERVER_NAME`` for its test client, appended to ALLOWED_HOSTS
unconditionally by config/settings.py, and it was one command away from being minted
into a school's certificate.

These tests hold four things:

1. a device can enrol from a URL instead of a file -- fingerprint, QR, and the CA;
2. the page works over PLAIN HTTP, because a device reaches it BEFORE it trusts the
   box, and redirecting it to https shows the warning it came to fix;
3. the private key is not reachable from any route, and neither file can reach git;
4. ``testserver`` never lands in a certificate -- while remaining in ALLOWED_HOSTS,
   because production code drives Django's test client at runtime.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.http import Http404, HttpResponse
from django.test import (
    RequestFactory,
    SimpleTestCase,
    TestCase,
    override_settings,
)
from django.urls import reverse, set_urlconf

from apps.schools import edge_tls
from apps.schools.views_edge_trust import (
    CA_CONTENT_TYPE,
    edge_trust_ca,
    edge_trust_page,
)

BOX = {
    # build_absolute_uri() validates the Host header, and a box is reached at an
    # address the test settings have never heard of -- which is the whole point.
    "ALLOWED_HOSTS": ["*"],
    "RMC_IS_SELFHOST_BOX": True,
    "RMC_IS_CLOUD_DEPLOYED": False,
    "USE_DJANGO_TENANTS": False,
    "ROOT_URLCONF": "config.tenant_urls",
}
NOT_A_BOX = {**BOX, "RMC_IS_SELFHOST_BOX": False, "SINGLE_TENANT": False}


class TenantUrlconfMixin:
    """Resolve names the way a box does.

    ``reverse()`` reads the THREAD-LOCAL urlconf that middleware installs, and only
    falls back to ROOT_URLCONF when none is set -- so ``override_settings`` alone is
    not enough once anything in the process has called ``set_urlconf``. On a real box
    ``UrlConfSwitcherMiddleware`` sets ``config.tenant_urls`` for exactly these hosts;
    this does the same, and puts it back afterwards.
    """

    def setUp(self):
        super().setUp()
        set_urlconf("config.tenant_urls")
        self.addCleanup(set_urlconf, None)


class TestServerNeverReachesACertificateTests(SimpleTestCase):
    """It stays an allowed host. It never becomes a certificate entry."""

    def test_testserver_is_dropped_from_certificate_names(self):
        self.assertEqual(edge_tls.normalize_hostname("testserver"), "")

    def test_it_is_dropped_however_it_is_cased(self):
        for spelling in ("testserver", "TestServer", "TESTSERVER"):
            with self.subTest(spelling=spelling):
                self.assertEqual(edge_tls.normalize_hostname(spelling), "")

    def test_a_real_lan_name_is_still_kept(self):
        # The guard must not become a general-purpose filter.
        self.assertEqual(
            edge_tls.normalize_hostname("gilead-tech.school.lan"),
            "gilead-tech.school.lan",
        )

    def test_it_is_absent_from_the_san_candidates_of_a_realistic_host_list(self):
        dns, ips = edge_tls.san_candidates(
            environ={},
            allowed_hosts=[
                "localhost",
                "127.0.0.1",
                ".local",
                "gilead-tech.school.lan",
                "10.10.20.137",
                "testserver",
            ],
        )
        self.assertNotIn("testserver", dns)
        self.assertIn("gilead-tech.school.lan", dns)
        self.assertIn("10.10.20.137", ips)

    def test_it_is_still_an_allowed_host(self):
        # Deliberately NOT removed from ALLOWED_HOSTS: two production views
        # (accounts/views_migration, api/offline_replay_views) and five management
        # commands drive Django's test client at runtime, and its default
        # SERVER_NAME is testserver -- so removing it would raise DisallowedHost on
        # real requests. The certificate is the right place to draw the line.
        self.assertIn("testserver", settings.ALLOWED_HOSTS)


class TrustPageIsBoxOnlyTests(TenantUrlconfMixin, SimpleTestCase):
    """A control-plane host publishing a certificate authority is a phishing page."""

    def _get(self, path="/edge/trust/"):
        return RequestFactory().get(path, HTTP_HOST="10.10.20.137")

    def test_the_page_404s_when_this_is_not_a_box(self):
        with override_settings(**NOT_A_BOX):
            with self.assertRaises(Http404):
                edge_trust_page(self._get())

    def test_the_download_404s_when_this_is_not_a_box(self):
        with override_settings(**NOT_A_BOX):
            with self.assertRaises(Http404):
                edge_trust_ca(self._get("/edge/trust/ca.crt"))


class TrustPageRendersTests(TenantUrlconfMixin, SimpleTestCase):
    """What a person actually sees, with and without a certificate authority."""

    def _get(self):
        return RequestFactory().get("/edge/trust/", HTTP_HOST="10.10.20.137:10000")

    def test_a_box_with_no_ca_is_told_to_run_the_bootstrap(self):
        with tempfile.TemporaryDirectory() as empty:
            with override_settings(**BOX), mock.patch.dict(
                os.environ, {edge_tls.ENV_DIR: empty}, clear=False
            ):
                response = edge_trust_page(self._get())
        body = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("edge-bootstrap.sh", body)

    def test_a_box_with_a_ca_shows_its_fingerprint_and_a_qr(self):
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory,
                dns_names=["gilead-tech.local"],
                ip_addresses=["10.10.20.137"],
                days=30,
            )
            with override_settings(**BOX), mock.patch.dict(
                os.environ, {edge_tls.ENV_DIR: directory}, clear=False
            ):
                response = edge_trust_page(self._get())
                _cert, _key, ca_path = edge_tls.certificate_paths()
                expected = edge_tls.inspect_certificate(ca_path).fingerprint
        body = response.content.decode("utf-8")
        self.assertIn(expected, body)
        # The QR is inlined so the page is ONE request and needs no static pipeline.
        self.assertIn("data:image/png;base64,", body)

    def test_the_page_carries_the_step_devices_actually_skip(self):
        # iOS installs the profile and still warns until Certificate Trust Settings
        # is switched on; Android's "install from storage" lands in the wrong store.
        # These live on the has-a-CA branch: a box with nothing to install is told to
        # run the bootstrap instead, and per-platform steps there would be noise.
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory,
                dns_names=["gilead-tech.local"],
                ip_addresses=["10.10.20.137"],
                days=30,
            )
            with override_settings(**BOX), mock.patch.dict(
                os.environ, {edge_tls.ENV_DIR: directory}, clear=False
            ):
                body = edge_trust_page(self._get()).content.decode("utf-8")
        self.assertIn("Certificate Trust Settings", body)
        self.assertIn("CA certificate", body)


class CaDownloadTests(TenantUrlconfMixin, SimpleTestCase):
    """Public by design -- and only the public half."""

    def _get(self):
        return RequestFactory().get("/edge/trust/ca.crt", HTTP_HOST="10.10.20.137")

    def test_it_serves_the_ca_with_the_type_a_phone_installs(self):
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory,
                dns_names=["gilead-tech.local"],
                ip_addresses=["10.10.20.137"],
                days=30,
            )
            with override_settings(**BOX), mock.patch.dict(
                os.environ, {edge_tls.ENV_DIR: directory}, clear=False
            ):
                response = edge_trust_ca(self._get())
                _cert, _key, ca_path = edge_tls.certificate_paths()
                on_disk = Path(ca_path).read_bytes()
                served = b"".join(response.streaming_content)
                # FileResponse holds the handle open; Windows refuses to delete the
                # temporary directory underneath it.
                response.close()
                # It is the CA, not the leaf: a leaf cannot be installed as a trust
                # anchor on Android or in Chrome's own store. Read INSIDE the
                # temporary directory -- inspecting a deleted file reports
                # self_signed=False and would look like a real finding.
                ca_facts = edge_tls.inspect_certificate(ca_path)
        self.assertEqual(response["Content-Type"], CA_CONTENT_TYPE)
        self.assertEqual(served, on_disk)
        self.assertTrue(ca_facts.self_signed)
        self.assertTrue(ca_facts.fingerprint)

    def test_a_box_with_no_ca_404s_rather_than_serving_nothing(self):
        with tempfile.TemporaryDirectory() as empty:
            with override_settings(**BOX), mock.patch.dict(
                os.environ, {edge_tls.ENV_DIR: empty}, clear=False
            ):
                with self.assertRaises(Http404):
                    edge_trust_ca(self._get())

    def test_the_view_takes_no_path_from_the_request(self):
        # There is no parameter to traverse and no branch that could reach ca.key or
        # the .p12 bundle. Asserted on the source so a later refactor cannot quietly
        # introduce one.
        import inspect

        from apps.schools import views_edge_trust

        # The FUNCTIONS, not the module: the module docstring explains that ca.key is
        # unreachable, and a substring search over prose would trip on the
        # explanation rather than on any code.
        source = inspect.getsource(views_edge_trust.edge_trust_ca) + inspect.getsource(
            views_edge_trust._ca_path
        )
        for forbidden in ("request.GET", "request.POST", "ca.key", ".p12"):
            self.assertNotIn(forbidden, source)


class PlainHttpIsLoadBearingTests(SimpleTestCase):
    """Redirect this page to https and it is a chicken-and-egg."""

    def test_the_trust_path_is_exempt_from_the_ssl_redirect(self):
        exempt = list(getattr(settings, "SECURE_REDIRECT_EXEMPT", []))
        self.assertTrue(
            any(re.match(pattern, "edge/trust/") for pattern in exempt),
            f"nothing in SECURE_REDIRECT_EXEMPT matches edge/trust/: {exempt}",
        )

    def test_the_download_is_exempt_too(self):
        exempt = list(getattr(settings, "SECURE_REDIRECT_EXEMPT", []))
        self.assertTrue(
            any(re.match(pattern, "edge/trust/ca.crt") for pattern in exempt)
        )


class PlainHttpIsNotAnAccidentTests(SimpleTestCase):
    """SECURE_REDIRECT_EXEMPT is load-bearing, so prove it against the real gate.

    Driving this through the test client cannot prove it: SecurityMiddleware reads
    SECURE_SSL_REDIRECT once in ``__init__``, and the client's handler caches its
    middleware, so an override_settings that arrives later changes nothing and the
    assertion passes on a box where the redirect was simply off. Build the
    middleware inside the override and ask it directly.
    """

    def _middleware(self):
        from django.middleware.security import SecurityMiddleware

        return SecurityMiddleware(lambda request: HttpResponse("ok"))

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_the_gate_is_armed_for_an_ordinary_page(self):
        # The control. Without this, the next test proves nothing.
        #
        # Deliberately NOT "/": SECURE_REDIRECT_EXEMPT already carries `^$`, so the
        # site root is exempt too and would have made this control pass while
        # proving nothing about the entry this file is here to protect. Django
        # matches against `request.path.lstrip("/")`, which is "" for the root.
        response = self._middleware()(RequestFactory().get("/dashboard/", secure=False))
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].startswith("https://"))

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_trust_enrolment_is_exempt_from_that_same_gate(self):
        for target in ("/edge/trust/", "/edge/trust/ca.crt"):
            with self.subTest(path=target):
                response = self._middleware()(
                    RequestFactory().get(target, secure=False)
                )
                self.assertEqual(
                    response.status_code,
                    200,
                    "a device reaches this page BECAUSE https warns; redirecting "
                    "it to https shows the very warning it came to fix",
                )

    def test_the_exempt_entry_is_actually_in_settings(self):
        # Belt and braces: the two tests above would both pass if the pattern were
        # deleted AND SECURE_SSL_REDIRECT stopped being read.
        patterns = list(getattr(settings, "SECURE_REDIRECT_EXEMPT", []))
        self.assertIn(r"^edge/trust/", patterns)


class TheAddressHandedOutIsTheBoxTests(SimpleTestCase):
    """A device must never be sent off the LAN to fetch a certificate authority.

    config/settings.py appends the canonical domain and its wildcard to
    ALLOWED_HOSTS on EVERY deployment, a box included -- the same settings module
    runs there. So the platform's public domain arrives in a box's own address list
    looking exactly like a school's hostname, and "the first real name" picks it.

    A device sent there either has no route off the LAN, or reaches the CLOUD, which
    404s this page by design. Caught by running the readiness command rather than
    reading it: it reported http://runmycampus.com:10000/edge/trust/ as the address
    a school's devices should use.
    """

    PLATFORM = ("runmycampus.com",)

    def test_the_platform_domain_is_never_the_enrolment_address(self):
        url = edge_tls.trust_enrolment_url(
            ["localhost", "runmycampus.com"],
            ["10.10.20.137"],
            exclude_public=self.PLATFORM,
        )
        self.assertEqual(url, "http://10.10.20.137:10000/edge/trust/")

    def test_a_subdomain_of_the_platform_is_refused_too(self):
        url = edge_tls.trust_enrolment_url(
            ["manager.runmycampus.com", "gilead.runmycampus.com"],
            ["10.0.0.9"],
            exclude_public=self.PLATFORM,
        )
        self.assertEqual(url, "http://10.0.0.9:10000/edge/trust/")

    def test_the_school_own_name_still_wins_over_an_ip(self):
        url = edge_tls.trust_enrolment_url(
            ["runmycampus.com", "gilead-tech.local"],
            ["10.0.0.9"],
            exclude_public=self.PLATFORM,
        )
        self.assertEqual(url, "http://gilead-tech.local:10000/edge/trust/")

    def test_a_name_that_merely_ENDS_with_the_domain_text_is_not_a_subdomain(self):
        # "notrunmycampus.com" is somebody else's domain, not ours -- the check is
        # on a label boundary, not a string suffix.
        url = edge_tls.trust_enrolment_url(
            ["notrunmycampus.com"], [], exclude_public=self.PLATFORM
        )
        self.assertEqual(url, "http://notrunmycampus.com:10000/edge/trust/")

    def test_only_the_platform_domain_is_left_so_no_url_is_offered(self):
        self.assertEqual(
            edge_tls.trust_enrolment_url(
                ["localhost", "runmycampus.com"], [], exclude_public=self.PLATFORM
            ),
            "",
        )

    @override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
    def test_it_reads_the_real_setting_when_not_told(self):
        # The default path, which is what every caller actually uses.
        url = edge_tls.trust_enrolment_url(["runmycampus.com"], ["10.0.0.9"])
        self.assertEqual(url, "http://10.0.0.9:10000/edge/trust/")

    def test_a_dotted_wildcard_entry_is_matched_as_the_domain(self):
        self.assertTrue(
            edge_tls._is_platform_public(".runmycampus.com", self.PLATFORM)
        )
        self.assertFalse(edge_tls._is_platform_public("", self.PLATFORM))


class TrustEnrolmentSurvivesTheSchoolNotResolvingTests(SimpleTestCase):
    """The prefix skip that keeps the page alive on a half-configured box.

    Asserted at the middleware's own constant so a future edit to the skip lists
    cannot quietly drop it. The end-to-end proof lives in
    TheWholeStackLetsADeviceThroughTests; this is the cheap regression guard.
    """

    def test_the_prefix_is_declared(self):
        from apps.schools import middleware as mw

        self.assertIn("/edge/trust/", mw.TRUST_ENROLMENT_PREFIXES)

    def test_both_school_resolving_middlewares_skip_it(self):
        source = (
            Path(settings.BASE_DIR)
            .joinpath("apps", "schools", "middleware.py")
            .read_text(encoding="utf-8")
        )
        # Two separate skip lists resolve a school; the page must be absent from
        # neither, and there is no single place that would fail loudly if it were.
        self.assertEqual(source.count("+ TRUST_ENROLMENT_PREFIXES"), 2)

    def test_the_prefix_matches_the_route(self):
        from apps.schools import middleware as mw

        self.assertTrue(
            edge_tls.TRUST_ENROLMENT_PATH.startswith(mw.TRUST_ENROLMENT_PREFIXES[0])
        )


class ItAnswersWhileTheDatabaseIsUselessTests(TestCase):
    """Zero queries. Not "few" -- zero.

    This is the page a device reaches when the box has just booted and is still
    migrating, and it is reached over plain http BECAUSE nothing on the box can be
    reached over https until it works. Every query it makes is a way for it to fail
    at exactly that moment.

    `render()` would run every context processor -- brand payload, tenant runtime,
    theme, feature flags -- and each of those queries. The view uses
    `render_to_string` with no request for this reason, and this test is what keeps
    somebody from "fixing" that back to `render()` later.
    """

    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        edge_tls.issue_self_signed(
            directory.name,
            dns_names=["box.local"],
            ip_addresses=["10.0.0.5"],
            days=30,
        )
        patcher = mock.patch.dict(
            os.environ, {edge_tls.ENV_DIR: directory.name}, clear=False
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @override_settings(**BOX)
    def test_the_page_makes_no_query_at_all(self):
        set_urlconf("config.tenant_urls")
        self.addCleanup(set_urlconf, None)
        request = RequestFactory().get("/edge/trust/")
        with self.assertNumQueries(0):
            response = edge_trust_page(request)
        self.assertEqual(response.status_code, 200)

    @override_settings(**BOX)
    def test_the_download_makes_no_query_either(self):
        set_urlconf("config.tenant_urls")
        self.addCleanup(set_urlconf, None)
        request = RequestFactory().get("/edge/trust/ca.crt")
        with self.assertNumQueries(0):
            response = edge_trust_ca(request)
        self.assertEqual(response.status_code, 200)
        response.close()


class ACorruptCaIsItsOwnStateTests(TenantUrlconfMixin, SimpleTestCase):
    """"Is there a file" is the wrong question to ask about a certificate.

    A truncated or corrupt ca.crt exists happily. Treated as a normal CA it renders
    an EMPTY fingerprint box beside a live Download button -- and comparing that
    fingerprint against the box console is the entire security model here. An empty
    box does not read as "something is wrong"; it reads as "just click Download".
    """

    def _corrupt(self, directory):
        Path(directory, "ca.crt").write_bytes(
            b"-----BEGIN CERTIFICATE-----" + b"\n" + b"truncated" + b"\n"
        )

    def _get(self):
        return RequestFactory().get("/edge/trust/")

    def test_the_page_says_so_instead_of_showing_an_empty_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            self._corrupt(directory)
            with override_settings(**BOX), mock.patch.dict(
                os.environ, {edge_tls.ENV_DIR: directory}, clear=False
            ):
                response = edge_trust_page(self._get())
        body = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("cannot be read", body)
        # And crucially, no download button to click past the missing fingerprint.
        self.assertNotIn("Download the certificate", body)

    def test_it_does_not_tell_you_to_mint_another_one(self):
        # "Run the bootstrap" is the WRONG advice for a file that already exists:
        # minting a second CA strands every device that trusted the first, and that
        # is the one irreversible action in this whole subsystem.
        with tempfile.TemporaryDirectory() as directory:
            self._corrupt(directory)
            with override_settings(**BOX), mock.patch.dict(
                os.environ, {edge_tls.ENV_DIR: directory}, clear=False
            ):
                response = edge_trust_page(self._get())
        body = response.content.decode("utf-8")
        self.assertNotIn("edge-bootstrap.sh", body)
        self.assertIn("import-ca", body)

    def test_the_download_refuses_rather_than_serving_broken_bytes(self):
        # A person who downloads a broken CA does not find out here. They find out
        # on the fourth device, and they blame the phone.
        with tempfile.TemporaryDirectory() as directory:
            self._corrupt(directory)
            with override_settings(**BOX), mock.patch.dict(
                os.environ, {edge_tls.ENV_DIR: directory}, clear=False
            ):
                with self.assertRaises(Http404):
                    edge_trust_ca(RequestFactory().get("/edge/trust/ca.crt"))

    def test_a_good_ca_is_still_served(self):
        # The control: the guard must not refuse a certificate that is fine.
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory,
                dns_names=["gilead-tech.local"],
                ip_addresses=["10.10.20.137"],
                days=30,
            )
            with override_settings(**BOX), mock.patch.dict(
                os.environ, {edge_tls.ENV_DIR: directory}, clear=False
            ):
                page = edge_trust_page(self._get())
                download = edge_trust_ca(RequestFactory().get("/edge/trust/ca.crt"))
                self.assertEqual(download.status_code, 200)
                download.close()
        body = page.content.decode("utf-8")
        self.assertIn("Download the certificate", body)
        self.assertNotIn("cannot be read", body)


class BothSurfacesShowTheSameFingerprintTests(TenantUrlconfMixin, SimpleTestCase):
    """Over plain http, a person comparing two numbers is the ONLY security here.

    The page says "check this against `manage.py edge_tls`". For a long time that
    command printed no fingerprint at all -- only the LEAF's subject and expiry --
    so the instruction pointed at output that did not contain the thing to compare.
    Somebody following it finds nothing, shrugs, and clicks Download, which is the
    exact behaviour the page exists to prevent.

    It must be the CA's fingerprint on both, not the leaf's. They are different
    certificates: devices install the CA, and the leaf is reissued underneath it
    every time the box changes address -- so a leaf fingerprint would stop matching
    the moment DHCP moved the box, and the page would start crying wolf.
    """

    def test_the_page_and_the_command_print_the_same_number(self):
        from io import StringIO

        from django.core.management import call_command

        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory,
                dns_names=["gilead-tech.local"],
                ip_addresses=["10.10.20.137"],
                days=825,
            )
            env = {
                edge_tls.ENV_DIR: directory,
                edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
            }
            with override_settings(**BOX), mock.patch.dict(
                os.environ, env, clear=False
            ):
                ca_fingerprint = edge_tls.inspect_certificate(
                    os.path.join(directory, "ca.crt")
                ).fingerprint
                page = edge_trust_page(RequestFactory().get("/edge/trust/"))
                console = StringIO()
                call_command("edge_tls", stdout=console)

        self.assertTrue(ca_fingerprint, "the fixture did not produce a fingerprint")
        body = page.content.decode("utf-8")
        printed = console.getvalue()

        self.assertIn(ca_fingerprint, body, "the PAGE does not show the CA fingerprint")
        self.assertIn(
            ca_fingerprint,
            printed,
            "`manage.py edge_tls` does not print the CA fingerprint, so the "
            "instruction on the page points at nothing to compare",
        )

    def test_it_is_the_CA_fingerprint_and_not_the_leaf(self):
        # If these two were ever the same certificate the test above would pass
        # while the design was wrong, so pin them apart.
        from io import StringIO

        from django.core.management import call_command

        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory,
                dns_names=["gilead-tech.local"],
                ip_addresses=["10.10.20.137"],
                days=825,
            )
            ca = edge_tls.inspect_certificate(os.path.join(directory, "ca.crt"))
            leaf = edge_tls.inspect_certificate(os.path.join(directory, "tls.crt"))
            self.assertNotEqual(ca.fingerprint, leaf.fingerprint)
            env = {
                edge_tls.ENV_DIR: directory,
                edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
            }
            with override_settings(**BOX), mock.patch.dict(
                os.environ, env, clear=False
            ):
                page = edge_trust_page(RequestFactory().get("/edge/trust/"))
                console = StringIO()
                call_command("edge_tls", stdout=console)

        body = page.content.decode("utf-8")
        self.assertNotIn(
            leaf.fingerprint,
            body,
            "the page shows the LEAF fingerprint -- it would stop matching the "
            "moment the box changed address and the leaf was reissued",
        )
        self.assertIn(ca.fingerprint, console.getvalue())


class TheDarkThemeCannotBeUndoneByOrderingTests(SimpleTestCase):
    """It shipped once with light text on white cards. On a phone. In a corridor.

    The dark ``@media`` block sat ABOVE the component rules. At equal specificity
    the later rule wins, so ``.card`` / ``.fp`` / ``.warn`` snapped back to their
    light backgrounds while ``body`` -- defined before the block -- stayed dark.
    Every device in dark mode got near-white text on a white card, and the
    FINGERPRINT, the one thing a person opens this page to read and the only
    security this page has, was invisible.

    Structural rather than visual, because nothing here can screenshot a phone: if
    every colour resolves from a custom property, and the dark block only ever
    redefines those properties, then no ordering can separate a surface from the
    ink meant to sit on it.
    """

    def _style(self):
        text = (
            Path(settings.BASE_DIR)
            .joinpath("templates", "schools", "edge_trust.html")
            .read_text(encoding="utf-8")
        )
        return text.split("<style>", 1)[1].split("</style>", 1)[0]

    def test_no_colour_is_declared_with_a_bare_hex_outside_the_token_blocks(self):
        style = self._style()
        without_tokens = re.sub(r":root\s*\{[^}]*\}", "", style)
        offenders = re.findall(
            r"^[^\n]*(?:background|color)\s*:\s*#[0-9A-Fa-f]{3,8}[^\n]*$",
            without_tokens,
            re.M,
        )
        self.assertEqual(
            offenders,
            [],
            "a colour is pinned to a literal outside :root, so it cannot follow the "
            "theme: " + "; ".join(o.strip() for o in offenders),
        )

    def test_the_dark_block_redefines_only_tokens(self):
        # The actual bug: a dark block that restyles COMPONENTS has to win on
        # ordering, and one day it will not.
        style = self._style()
        match = re.search(
            r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{(.*?)\n    \}",
            style,
            re.S,
        )
        self.assertIsNotNone(match, "no dark-mode block found at all")
        body = match.group(1)
        selectors = re.findall(r"([^{};]+)\{", body)
        self.assertTrue(selectors, "dark block declares nothing")
        for selector in selectors:
            self.assertEqual(
                selector.strip(),
                ":root",
                "the dark block restyles a component instead of redefining tokens; "
                "that is what made the fingerprint invisible",
            )

    def test_every_token_used_is_actually_defined(self):
        style = self._style()
        used = set(re.findall(r"var\((--[a-z-]+)\)", style))
        defined = set(re.findall(r"^\s*(--[a-z-]+)\s*:", style, re.M))
        self.assertTrue(used, "no tokens are referenced at all")
        self.assertEqual(
            used - defined, set(), "a var() with no definition renders as nothing"
        )

    def test_both_themes_define_the_same_token_set(self):
        # A token defined in light but not dark silently keeps its light value on a
        # dark ground -- the same class of bug, one shade quieter.
        style = self._style()
        blocks = re.findall(r":root\s*\{([^}]*)\}", style)
        self.assertGreaterEqual(len(blocks), 2, "expected a light and a dark :root")
        names = [set(re.findall(r"(--[a-z-]+)\s*:", b)) for b in blocks]
        light, dark = names[0], names[1]
        self.assertEqual(
            light - dark,
            set(),
            "these tokens have no dark value and will keep the light one: "
            + ", ".join(sorted(light - dark)),
        )

    def test_the_fingerprint_panel_sets_its_own_colour(self):
        # It must never inherit a muted/secondary colour: it is the thing the page
        # exists to show, and it is compared character by character.
        style = self._style()
        panel = re.search(r"\.fp\s*\{([^}]*)\}", style)
        self.assertIsNotNone(panel)
        self.assertIn("color:", panel.group(1))


class CaMaterialCannotReachGitTests(SimpleTestCase):
    """box-ca-bundle.p12 carries the CA private key. /srv/rmc is a git tree."""

    def _repo_file(self, *parts):
        return Path(settings.BASE_DIR).joinpath(*parts)

    def test_the_bootstrap_writes_outside_the_repo_by_default(self):
        script = self._repo_file("deploy", "selfhost", "edge-bootstrap.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('OUT_DIR="${RMC_EDGE_OUT_DIR:-$(dirname "$REPO")}"', script)
        self.assertNotIn('OUT_DIR="${RMC_EDGE_OUT_DIR:-$REPO}"', script)

    def test_both_names_are_gitignored_as_the_second_lock(self):
        ignored = self._repo_file(".gitignore").read_text(encoding="utf-8")
        self.assertIn("box-ca-bundle.p12", ignored)
        self.assertIn("box-ca.crt", ignored)


class EnrolmentUrlIsOneValueTests(TenantUrlconfMixin, SimpleTestCase):
    """Four surfaces print this URL. They must all print the same one.

    The bootstrap banner, ``edge_bootstrap``, ``edge_tls`` and the generated
    onboarding runbook each tell a school where to send its devices. A URL that
    drifts from its route is worse than no URL: it is a page nobody can find, on an
    afternoon somebody set aside for walking round a building.
    """

    def test_the_constant_is_the_route(self):
        # The one assertion that makes the constant safe to print from anywhere.
        self.assertEqual(edge_tls.TRUST_ENROLMENT_PATH, reverse("edge_trust"))

    def test_a_dns_name_wins_over_an_ip(self):
        # Not cosmetic. The leaf can be reissued onto a new address without anybody
        # revisiting a device -- but only if what people wrote down was a name.
        url = edge_tls.trust_enrolment_url(["gilead-tech.local"], ["10.10.20.137"])
        self.assertEqual(url, "http://gilead-tech.local:10000/edge/trust/")

    def test_localhost_is_never_the_address_handed_out(self):
        # localhost is on every box's certificate and is the one address that means
        # "not this box" to a phone in a corridor.
        url = edge_tls.trust_enrolment_url(["localhost", "school.lan"], [])
        self.assertEqual(url, "http://school.lan:10000/edge/trust/")

    def test_a_loopback_ip_is_refused_the_same_way(self):
        url = edge_tls.trust_enrolment_url(["localhost"], ["127.0.0.1", "10.10.20.137"])
        self.assertEqual(url, "http://10.10.20.137:10000/edge/trust/")

    def test_no_reachable_address_yields_no_url_rather_than_a_wrong_one(self):
        # A banner printing http://:10000/edge/trust/ is worse than a banner that
        # says nothing: somebody would try it.
        self.assertEqual(edge_tls.trust_enrolment_url([], []), "")
        self.assertEqual(edge_tls.trust_enrolment_url(["localhost"], ["127.0.0.1"]), "")

    def test_an_ipv6_address_is_bracketed_or_the_port_reads_as_a_hextet(self):
        url = edge_tls.trust_enrolment_url([], ["fd00::1"])
        self.assertEqual(url, "http://[fd00::1]:10000/edge/trust/")

    def test_the_published_port_comes_from_the_box_environment(self):
        # compose maps ${WEB_PORT:-10000} onto the container's 10000 AND .env carries
        # WEB_PORT, so env_file: puts it in the container environment. That is the
        # only reason a process INSIDE the container can name the port that reaches
        # it from OUTSIDE.
        with mock.patch.dict(os.environ, {"WEB_PORT": "8443"}):
            url = edge_tls.trust_enrolment_url(["school.lan"], [])
        self.assertEqual(url, "http://school.lan:8443/edge/trust/")

    def test_it_is_http_and_never_https(self):
        # The whole point. A device arrives BECAUSE https warns; sending it to https
        # is the chicken-and-egg this page exists to break.
        url = edge_tls.trust_enrolment_url(["school.lan"], ["10.0.0.5"])
        self.assertTrue(url.startswith("http://"), url)
        self.assertNotIn("https://", url)

    def test_the_wizard_does_not_keep_a_second_copy_of_the_port(self):
        from apps.schools import edge_onboarding

        self.assertIs(edge_onboarding.DEFAULT_WEB_PORT, edge_tls.DEFAULT_WEB_PORT)


class RunbookSurfacesAllPointAtThePageTests(SimpleTestCase):
    """The chore that said "install ca.crt on the devices" is gone from every one."""

    def _read(self, *parts):
        return Path(settings.BASE_DIR).joinpath(*parts).read_text(encoding="utf-8")

    def test_the_bootstrap_command_sends_people_to_the_url(self):
        source = self._read(
            "apps", "schools", "management", "commands", "edge_bootstrap.py"
        )
        self.assertIn("edge_tls.trust_enrolment_url(dns, ips)", source)
        # The old step 2 told a person to carry a file to every device.
        self.assertNotIn("Install ca.crt on the devices", source)

    def test_it_stays_quiet_when_this_run_did_not_check_the_terminator(self):
        # An ordering guard, not tidiness. The expensive failure here is a
        # terminator serving Caddy's OWN certificate authority while every log says
        # healthy -- and a run that skipped the check cannot tell. The shell script
        # passes --terminator '' because it starts, restarts and checks Caddy
        # itself, several steps later; it prints the URL once that has passed.
        source = self._read(
            "apps", "schools", "management", "commands", "edge_bootstrap.py"
        )
        self.assertIn("if trust_url and checked_terminator:", source)
        self.assertIn(
            'checked_terminator = bool(str(options["terminator"] or "").strip())',
            source,
        )

    def test_the_edge_tls_command_sends_people_to_the_url(self):
        source = self._read("apps", "schools", "management", "commands", "edge_tls.py")
        self.assertIn("trust_enrolment_url(", source)

    def test_the_bootstrap_script_asks_for_the_url_rather_than_building_one(self):
        script = self._read("deploy", "selfhost", "edge-bootstrap.sh")
        self.assertIn("--trust-url", script)
        self.assertIn("TRUST_URL", script)
        # The ratchet that matters. Building this URL in shell needs the published
        # port AND the which-of-our-names-do-we-hand-out rule; both already live in
        # edge_tls, where they are tested. A second copy in shell is an answer that
        # drifts silently, and it drifts into a URL nobody can open -- discovered by
        # a school, in a corridor, on the afternoon set aside for this.
        directives = "\n".join(
            line for line in script.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertNotIn(
            edge_tls.TRUST_ENROLMENT_PATH,
            directives,
            "edge-bootstrap.sh spells the enrolment path itself; ask the app "
            "(`edge_tls --trust-url`) so there is one answer, not two.",
        )

    def test_the_trust_url_flag_exists_and_prints_only_a_url(self):
        # A caller does URL=$(... --trust-url); anything else on stdout ends up
        # inside the URL. Proven by running the command, not by reading it.
        from io import StringIO

        from django.core.management import call_command

        buffer = StringIO()
        with mock.patch.dict(os.environ, {"WEB_PORT": "10000"}), override_settings(
            ALLOWED_HOSTS=["localhost", "gilead-tech.local", "10.10.20.137"]
        ):
            call_command("edge_tls", "--trust-url", stdout=buffer)
        printed = buffer.getvalue().strip()
        self.assertEqual(printed, "http://gilead-tech.local:10000/edge/trust/")

    def test_the_flag_stays_silent_rather_than_printing_a_url_with_a_hole_in_it(self):
        from io import StringIO

        from django.core.management import call_command

        buffer = StringIO()
        with override_settings(ALLOWED_HOSTS=["localhost"]):
            call_command("edge_tls", "--trust-url", stdout=buffer)
        self.assertEqual(buffer.getvalue().strip(), "")

    def test_the_onboarding_wizard_runbook_builds_it_from_the_constant(self):
        from apps.schools import edge_onboarding

        source = self._read("apps", "schools", "edge_onboarding.py")
        self.assertIn("edge_tls.TRUST_ENROLMENT_PATH", source)
        # And prove it end to end, not just by grep: the generated runbook must
        # contain a URL a person could actually type.
        runbook = edge_onboarding._runbook(
            mode=edge_tls.MODE_SELF_SIGNED,
            dns_names=["gilead-tech.local"],
            ip_addresses=["10.10.20.137"],
            mobility=edge_onboarding.MOVE_NEVER,
            web_port="8443",
        )
        joined = "\n".join(runbook)
        self.assertIn("http://gilead-tech.local:8443/edge/trust/", joined)
        # The chore this replaced must not have survived anywhere in it.
        self.assertNotIn("USB", joined)

    def test_the_tls_runbook_documents_it(self):
        runbook = self._read("docs", "EDGE_TLS_RUNBOOK.md")
        self.assertIn("/edge/trust/", runbook)


@override_settings(
    ROOT_URLCONF="config.tenant_urls",
    SINGLE_TENANT="1",
    ALLOWED_HOSTS=["*"],
    SECURE_SSL_REDIRECT=True,
)
class TheWholeStackLetsADeviceThroughTests(TestCase):
    """The one test that matches what actually happens in a corridor.

    A phone, nobody signed in, plain http, on a box that redirects everything else
    to https. If any gate in the stack answers first, the school never sees the
    page -- and the symptom is a redirect into the https warning this page exists
    to remove.
    """

    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        edge_tls.issue_self_signed(
            directory.name,
            dns_names=["box.local"],
            ip_addresses=["10.0.0.5"],
            days=30,
        )
        patcher = mock.patch.dict(
            os.environ, {edge_tls.ENV_DIR: directory.name}, clear=False
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_anonymous_device_gets_the_page_over_plain_http(self):
        response = self.client.get("/edge/trust/", secure=False, HTTP_HOST="box.local")
        self.assertEqual(
            response.status_code,
            200,
            "something in the middleware stack answered before the view: "
            f"{response.status_code} -> {response.get('Location', '')}",
        )
        self.assertIn("Trust this box", response.content.decode("utf-8"))

    def test_the_certificate_download_survives_the_stack_too(self):
        response = self.client.get(
            "/edge/trust/ca.crt", secure=False, HTTP_HOST="box.local"
        )
        self.assertEqual(
            response.status_code,
            200,
            f"{response.status_code} -> {response.get('Location', '')}",
        )
        self.assertEqual(response["Content-Type"], "application/x-x509-ca-cert")
        # Windows will not delete the temp directory while the handle is open.
        response.close()

    def test_the_school_layer_no_longer_answers_first(self):
        # The regression this class was written for. A box whose school does not
        # resolve -- just booted, mid-migration, no school row yet -- used to send
        # the device to https://<base-domain>/school-not-found/. On a school LAN
        # with no route to the internet that is a browser error, not a 404 page,
        # and the person holding the phone cannot tell those apart.
        response = self.client.get("/edge/trust/", secure=False, HTTP_HOST="box.local")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("school-not-found", response.get("Location", ""))


class ComposeKnobsTests(SimpleTestCase):
    """A value a box has to hand-edit is a value that fights every git pull."""

    def _compose(self):
        return (
            Path(settings.BASE_DIR)
            .joinpath("deploy", "selfhost", "docker-compose.yml")
            .read_text(encoding="utf-8")
        )

    def test_max_connections_is_a_knob_not_a_literal(self):
        compose = self._compose()
        self.assertIn("max_connections=${POSTGRES_MAX_CONNECTIONS:-200}", compose)

    def test_the_default_is_above_the_postgres_stock_100(self):
        # 4 gunicorn workers x 4 threads, plus a celery worker and beat, is already
        # tight against the stock 100 -- and the failure mode is "sorry, too many
        # clients already" on a box that otherwise looks healthy.
        compose = self._compose()
        match = re.search(r"POSTGRES_MAX_CONNECTIONS:-(\d+)", compose)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(int(match.group(1)), 200)
