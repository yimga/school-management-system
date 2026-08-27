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
    edge_trust_probe,
    edge_trust_profile,
)
from apps.schools.views_edge_trust import _device_hint

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


class AnUnresolvableNameWarnsButMustNotHaltABoxTests(SimpleTestCase):
    """The enrolment hostname check is advisory on purpose.

    It resolves from INSIDE the container, whose resolver is not a phone's: a router
    DNS entry can be visible to every device on the LAN and invisible to Docker. So
    the check can be wrong in exactly the direction that matters.

    ``deploy/selfhost/entrypoint.web.sh`` runs this command on EVERY container start
    and honours ``RMC_EDGE_READINESS_STRICT=1``, where a FAIL raises CommandError
    under ``set -euo pipefail``. Promoting this line to FAIL would therefore refuse
    to boot an otherwise healthy box over a DNS inference -- while the box serves
    perfectly well at its IP the whole time.
    """

    def _source(self):
        return (
            Path(settings.BASE_DIR)
            .joinpath("apps", "schools", "management", "commands", "check_edge_readiness.py")
            .read_text(encoding="utf-8")
        )

    def test_the_unresolvable_branch_is_a_warn(self):
        source = self._source()
        marker = "does not resolve FROM THIS BOX"
        self.assertIn(marker, source)
        before = source.split(marker, 1)[0]
        # The severity is the argument of the findings.append() that carries it.
        opener = before.rfind("findings.append((")
        self.assertNotEqual(opener, -1)
        severity = before[opener:].split("((", 1)[1].split(",", 1)[0].strip()
        self.assertEqual(
            severity,
            "WARN",
            "an unresolvable enrolment hostname must not be able to halt a boot: "
            "the entrypoint runs this on every start and honours "
            "RMC_EDGE_READINESS_STRICT=1",
        )

    def test_the_resolver_cannot_hang_a_boot(self):
        source = self._source()
        self.assertIn("def _resolves(", source)
        # A daemon thread with a join timeout, so a slow resolver cannot hold a
        # school's box in a boot loop.
        self.assertIn("daemon=True", source)
        self.assertIn("worker.join(timeout_seconds)", source)

    def test_the_entrypoint_still_tolerates_a_non_strict_failure(self):
        entrypoint = (
            Path(settings.BASE_DIR)
            .joinpath("deploy", "selfhost", "entrypoint.web.sh")
            .read_text(encoding="utf-8")
        )
        self.assertIn("check_edge_readiness || true", entrypoint)


class TheDeviceCanBeToldWhetherItWorkedTests(TenantUrlconfMixin, SimpleTestCase):
    """Almost nobody finds out an install failed on the device they installed it on.

    They find out on the fourth device, a week later, and they blame the phone. The
    page can just ask: load a 1x1 PNG over https from this box. A device that trusts
    the box CA completes the handshake; one that does not, does not.

    Most of what is asserted here is the ways this could have quietly answered WRONG,
    because a check that reports "not trusted" about a trusting device is worse than
    no check at all -- it sends somebody to reinstall a CA that was already fine.
    """

    def _page(self, host, dns, ips, mode=edge_tls.MODE_SELF_SIGNED, https_port=""):
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory, dns_names=list(dns), ip_addresses=list(ips), days=825
            )
            env = {edge_tls.ENV_DIR: directory, edge_tls.ENV_MODE: mode}
            if https_port:
                env[edge_tls.ENV_HTTPS_PORT] = https_port
            with override_settings(**BOX), mock.patch.dict(
                os.environ, env, clear=False
            ):
                request = RequestFactory().get("/edge/trust/", HTTP_HOST=host)
                # What ContentSecurityPolicyMiddleware sets before the view runs.
                request.csp_nonce = "test-nonce-abc"
                return edge_trust_page(request).content.decode("utf-8")

    # -- the happy path ------------------------------------------------------------

    def test_a_device_at_an_address_the_certificate_covers_is_offered_the_check(self):
        body = self._page("gilead-tech.local", ["gilead-tech.local"], [])
        self.assertIn('id="rmc-verify"', body)
        self.assertIn(
            "https://gilead-tech.local/edge/trust/probe.png",
            body,
            "the probe must be aimed at the box over https, at the address the "
            "device actually used to get here",
        )

    def test_the_probe_carries_the_tls_port_when_it_is_not_443(self):
        # The compose file publishes EDGE_TLS_HTTPS_PORT; a probe aimed at 443 on a
        # box that terminates on 8443 reports "not trusted" about every device.
        body = self._page(
            "gilead-tech.local", ["gilead-tech.local"], [], https_port="8443"
        )
        self.assertIn("https://gilead-tech.local:8443/edge/trust/probe.png", body)

    def test_tls_port_reads_the_environment_and_defaults_to_443(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(edge_tls.ENV_HTTPS_PORT, None)
            self.assertEqual(edge_tls.tls_port(), "443")
        with mock.patch.dict(
            os.environ, {edge_tls.ENV_HTTPS_PORT: " 8443 "}, clear=False
        ):
            self.assertEqual(edge_tls.tls_port(), "8443")

    # -- the cases where offering a check would have LIED --------------------------

    def test_no_check_is_offered_when_the_box_serves_no_https_at_all(self):
        # There is no second address to check. A probe here fails for every device,
        # and "not trusted" would be a lie about a box that simply has TLS off.
        body = self._page(
            "gilead-tech.local", ["gilead-tech.local"], [], mode=edge_tls.MODE_OFF
        )
        self.assertNotIn('id="rmc-verify"', body)

    def test_an_address_outside_the_certificate_is_named_rather_than_probed(self):
        # The box KNOWS this one: the device reached it at an address the certificate
        # does not asssert, so https was always going to warn here whatever the
        # device installed. "Reissue the certificate" is a different instruction from
        # "install the CA", and a failed probe would have given the wrong one.
        body = self._page("10.10.20.137", ["gilead-tech.local"], [])
        self.assertNotIn('id="rmc-verify"', body)
        self.assertIn("10.10.20.137", body)
        self.assertIn("gilead-tech.local", body)
        self.assertIn("--issue-selfsigned", body)

    def test_the_failure_message_does_not_assert_a_cause_it_cannot_know(self):
        # A failed image load cannot distinguish "CA not installed" from "terminator
        # down" from "wrong port". Saying the first outright is how a readiness
        # message sends somebody to fix the wrong thing -- so it must name the
        # possibility that the box, not the device, is the problem.
        body = self._page("gilead-tech.local", ["gilead-tech.local"], [])
        message = body.split('id="rmc-msg-no"', 1)[1].split("</span>", 1)[0]
        self.assertIn("not answering", message)

    # -- the two CSP traps ---------------------------------------------------------

    def test_the_script_carries_the_nonce_the_middleware_set(self):
        # THE TRAP. `csp_nonce` normally arrives via a context processor, and this
        # page renders with a plain dict SO THAT no context processor runs -- so the
        # nonce would have been empty, script-src 'self' would have blocked the
        # script (CSP_ENFORCE defaults to 1), and the button would have done nothing
        # at all with nothing in the page to say why.
        body = self._page("gilead-tech.local", ["gilead-tech.local"], [])
        self.assertIn('nonce="test-nonce-abc"', body)

    def test_the_page_never_emits_a_script_with_an_empty_nonce(self):
        body = self._page("gilead-tech.local", ["gilead-tech.local"], [])
        self.assertNotIn('<script nonce=""', body)
        for match in re.findall(r"<script[^>]*>", body):
            self.assertIn(
                "nonce=", match, "an un-nonced inline script is a script that is blocked"
            )

    def test_the_probe_is_an_image_and_never_a_fetch(self):
        # THE OTHER TRAP. The page is http on the app port; the probe is https on the
        # TLS port -- a different ORIGIN. `connect-src 'self'` blocks a fetch there
        # outright, so the page would have reported "not trusted" about a device that
        # trusts the box perfectly well. `img-src` already carries `https:`.
        body = self._page("gilead-tech.local", ["gilead-tech.local"], [])
        script = body.split("<script", 1)[1]
        # Comments stripped: the block explains at length that it is deliberately
        # NOT a fetch, and an assertion that reads its own prose proves nothing.
        code = "\n".join(
            line
            for line in script.splitlines()
            if not line.strip().startswith("//")
        )
        self.assertNotIn("fetch(", code)
        self.assertNotIn("XMLHttpRequest", code)
        self.assertIn("new Image()", code)

    def test_no_inline_event_handler_attributes(self):
        # The M9 CSP enforce seal: a nonce cannot authorize an on*= ATTRIBUTE, so a
        # strict script-src blocks them. Property assignment in JS is fine.
        body = self._page("gilead-tech.local", ["gilead-tech.local"], [])
        offenders = re.findall(r"<[^>]*\son(?:click|load|error|submit)\s*=", body)
        self.assertEqual(offenders, [], "inline handlers are blocked under CSP")
        self.assertIn("addEventListener", body)

    # -- the endpoint itself -------------------------------------------------------

    def test_the_probe_endpoint_serves_a_real_png(self):
        with override_settings(**BOX):
            response = edge_trust_probe(RequestFactory().get("/edge/trust/probe.png"))
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(
            response.content.startswith(b"\x89PNG\r\n\x1a\n"),
            "a device cannot fire onload for something that is not an image",
        )

    def test_the_probe_is_not_served_off_a_box(self):
        with override_settings(**NOT_A_BOX):
            with self.assertRaises(Http404):
                edge_trust_probe(RequestFactory().get("/edge/trust/probe.png"))

    def test_the_probe_sits_under_the_prefix_the_tenant_middlewares_skip(self):
        # A box being set up is exactly a box whose school does not resolve yet. If
        # this route sat anywhere else, the middleware would answer with the
        # school-not-found redirect and the image would "fail" on every device.
        from apps.schools.middleware import TRUST_ENROLMENT_PREFIXES

        probe = reverse("edge_trust_probe")
        self.assertTrue(
            any(probe.startswith(prefix) for prefix in TRUST_ENROLMENT_PREFIXES),
            f"{probe} is not under a skipped prefix: {TRUST_ENROLMENT_PREFIXES}",
        )


class WhatAManagementConsoleActuallyWantsTests(TenantUrlconfMixin, SimpleTestCase):
    """On a managed fleet, step 3 should never happen at all.

    Every console can push a root CA to every enrolled device at once, and on Apple
    hardware a PUSHED profile is trusted on arrival while a hand-installed one still
    needs the Trust Settings screen. So the box builds the payloads rather than
    leaving an administrator to hand-write a plist.

    The identifiers being STABLE is the load-bearing property, not a detail: Apple
    replaces a profile carrying the same PayloadIdentifier and installs a second one
    when it differs. Random UUIDs would mean every re-push silently accumulates
    another trust anchor on every device in the school.
    """

    def _ca(self, directory, dns=("gilead-tech.local",), ips=("10.10.20.137",)):
        edge_tls.issue_self_signed(
            directory, dns_names=list(dns), ip_addresses=list(ips), days=825
        )
        return os.path.join(directory, "ca.crt")

    def test_the_profile_is_a_plist_carrying_a_root_payload(self):
        import plistlib

        with tempfile.TemporaryDirectory() as directory:
            document = plistlib.loads(edge_tls.mobileconfig(self._ca(directory)))
        self.assertEqual(document["PayloadType"], "Configuration")
        self.assertEqual(
            document["PayloadContent"][0]["PayloadType"],
            "com.apple.security.root",
            "any other payload type puts the certificate somewhere trust is never "
            "consulted from",
        )

    def test_the_certificate_inside_the_profile_is_this_box_ca(self):
        # The one that matters. A profile that installs cleanly and carries the WRONG
        # authority is worse than one that fails: it is a fleet-wide trust anchor
        # nobody has any reason to look at again.
        import plistlib

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes

        with tempfile.TemporaryDirectory() as directory:
            ca_path = self._ca(directory)
            document = plistlib.loads(edge_tls.mobileconfig(ca_path))
            embedded = x509.load_der_x509_certificate(
                document["PayloadContent"][0]["PayloadContent"]
            )
            with open(ca_path, "rb") as handle:
                on_disk = x509.load_pem_x509_certificate(handle.read())
        self.assertEqual(
            embedded.fingerprint(hashes.SHA256()),
            on_disk.fingerprint(hashes.SHA256()),
        )

    def test_the_same_ca_always_produces_the_same_identifiers(self):
        # Re-push REPLACES. Anything else accumulates trust anchors on every device.
        import plistlib

        with tempfile.TemporaryDirectory() as directory:
            ca_path = self._ca(directory)
            first = plistlib.loads(edge_tls.mobileconfig(ca_path))
            second = plistlib.loads(edge_tls.mobileconfig(ca_path))
        self.assertEqual(first["PayloadIdentifier"], second["PayloadIdentifier"])
        self.assertEqual(first["PayloadUUID"], second["PayloadUUID"])

    def test_a_different_ca_produces_different_identifiers(self):
        # Two boxes in one district must not have their profiles overwrite each other.
        import plistlib

        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            first = plistlib.loads(edge_tls.mobileconfig(self._ca(one)))
            second = plistlib.loads(
                edge_tls.mobileconfig(self._ca(two, dns=("other-school.local",)))
            )
        self.assertNotEqual(first["PayloadIdentifier"], second["PayloadIdentifier"])
        self.assertNotEqual(first["PayloadUUID"], second["PayloadUUID"])

    def test_the_display_name_comes_from_the_certificate_not_from_a_fixture(self):
        # Tenant-wide: nothing here may name one school. The CA subject is the only
        # per-box identity this page is allowed to read, because the page renders
        # with no database at all.
        import plistlib

        with tempfile.TemporaryDirectory() as directory:
            ca_path = self._ca(directory, dns=("st-mary-college.local",))
            document = plistlib.loads(edge_tls.mobileconfig(ca_path))
        self.assertIn("st-mary-college.local", document["PayloadDisplayName"])

    def test_an_unreadable_ca_yields_no_profile_rather_than_a_broken_one(self):
        with tempfile.TemporaryDirectory() as directory:
            broken = os.path.join(directory, "ca.crt")
            with open(broken, "w", encoding="utf-8") as handle:
                handle.write("-----BEGIN CERTIFICATE-----\nnope\n")
            self.assertEqual(edge_tls.mobileconfig(broken), b"")
            self.assertEqual(edge_tls.android_policy_snippet(broken), "")

    def test_the_android_snippet_decodes_back_to_the_certificate(self):
        import base64 as b64
        import json as js

        from cryptography import x509

        with tempfile.TemporaryDirectory() as directory:
            ca_path = self._ca(directory)
            payload = js.loads(edge_tls.android_policy_snippet(ca_path))
            der = b64.b64decode(payload["caCerts"][0])
        self.assertEqual(list(payload), ["caCerts"])
        x509.load_der_x509_certificate(der)  # raises if this is not a certificate

    # -- the served endpoint ---------------------------------------------------------

    def _serve(self, settings_override, directory):
        env = {
            edge_tls.ENV_DIR: directory,
            edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
        }
        with override_settings(**settings_override), mock.patch.dict(
            os.environ, env, clear=False
        ):
            return edge_trust_profile(
                RequestFactory().get("/edge/trust/box-ca.mobileconfig")
            )

    def test_the_profile_is_served_as_an_apple_configuration_profile(self):
        # Served as anything else, Safari files it in Downloads and the tap that was
        # meant to open the installer does nothing at all.
        with tempfile.TemporaryDirectory() as directory:
            self._ca(directory)
            response = self._serve(BOX, directory)
        self.assertEqual(response["Content-Type"], edge_tls.MOBILECONFIG_CONTENT_TYPE)
        self.assertIn(".mobileconfig", response["Content-Disposition"])

    def test_the_profile_is_not_served_off_a_box(self):
        with tempfile.TemporaryDirectory() as directory:
            self._ca(directory)
            with self.assertRaises(Http404):
                self._serve(NOT_A_BOX, directory)

    def test_a_corrupt_ca_refuses_rather_than_serving_an_empty_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "ca.crt"), "w", encoding="utf-8") as h:
                h.write("not a certificate")
            with self.assertRaises(Http404):
                self._serve(BOX, directory)


class TheExportFolderCannotCarryTheKeyTests(SimpleTestCase):
    """`--export-mdm` writes the folder most likely to be zipped up and emailed.

    Everything in it is public by design. The private key sits one directory away and
    is not: the difference between distributing a certificate authority and
    distributing the power to impersonate every site in the school is one filename,
    and it is worth a test rather than a careful reading.
    """

    def _run(self, out_dir, cert_dir):
        from io import StringIO

        from django.core.management import call_command

        env = {
            edge_tls.ENV_DIR: cert_dir,
            edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
        }
        console = StringIO()
        with mock.patch.dict(os.environ, env, clear=False):
            call_command("edge_tls", export_mdm=out_dir, stdout=console)
        return console.getvalue()

    def test_it_writes_what_each_console_needs(self):
        with tempfile.TemporaryDirectory() as certs, tempfile.TemporaryDirectory() as out:
            edge_tls.issue_self_signed(
                certs, dns_names=["gilead-tech.local"], ip_addresses=[], days=825
            )
            self._run(out, certs)
            written = sorted(os.listdir(out))
        self.assertEqual(
            written,
            ["README.txt", "android-policy.json", "box-ca.crt", "box-ca.mobileconfig"],
        )

    def test_no_private_key_material_reaches_the_export(self):
        with tempfile.TemporaryDirectory() as certs, tempfile.TemporaryDirectory() as out:
            edge_tls.issue_self_signed(
                certs, dns_names=["gilead-tech.local"], ip_addresses=[], days=825
            )
            # Prove the key was THERE to leak, or this test passes for the wrong reason.
            self.assertTrue(os.path.isfile(os.path.join(certs, "ca.key")))
            self._run(out, certs)
            for name in os.listdir(out):
                with open(os.path.join(out, name), "rb") as handle:
                    body = handle.read()
                self.assertNotIn(b"PRIVATE KEY", body, f"{name} carries key material")

    def test_it_refuses_to_write_beside_the_private_key(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with tempfile.TemporaryDirectory() as certs:
            edge_tls.issue_self_signed(
                certs, dns_names=["gilead-tech.local"], ip_addresses=[], days=825
            )
            env = {
                edge_tls.ENV_DIR: certs,
                edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
            }
            with mock.patch.dict(os.environ, env, clear=False):
                with self.assertRaises(CommandError) as caught:
                    call_command("edge_tls", export_mdm=certs)
        self.assertIn("PRIVATE KEY", str(caught.exception))

    def test_the_readme_carries_the_fingerprint_to_compare(self):
        # The folder gets forwarded. If the fingerprint is only in the covering
        # email, the person who ends up pushing it has nothing to check against.
        with tempfile.TemporaryDirectory() as certs, tempfile.TemporaryDirectory() as out:
            edge_tls.issue_self_signed(
                certs, dns_names=["gilead-tech.local"], ip_addresses=[], days=825
            )
            self._run(out, certs)
            with open(os.path.join(out, "README.txt"), encoding="utf-8") as handle:
                readme = handle.read()
            expected = edge_tls.inspect_certificate(
                os.path.join(certs, "ca.crt")
            ).fingerprint
        self.assertIn(expected, readme)


class ThePageOffersTheFileThisDeviceCanUseTests(TenantUrlconfMixin, SimpleTestCase):
    """An iPhone handed a raw .crt files it where the trust screen never looks.

    Sniffing decides ORDER only. Every platform's steps stay on the page and both
    downloads stay one click apart, so a wrong guess costs a click and can never cost
    correctness -- which is the only kind of decision a user-agent string is good
    enough to make.
    """

    APPLE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15"
    ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/125"
    WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125"

    def _page(self, agent):
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory,
                dns_names=["gilead-tech.local"],
                ip_addresses=[],
                days=825,
            )
            env = {
                edge_tls.ENV_DIR: directory,
                edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
            }
            with override_settings(**BOX), mock.patch.dict(
                os.environ, env, clear=False
            ):
                request = RequestFactory().get(
                    "/edge/trust/",
                    HTTP_HOST="gilead-tech.local",
                    HTTP_USER_AGENT=agent,
                )
                request.csp_nonce = "n"
                return edge_trust_page(request).content.decode("utf-8")

    def test_an_apple_device_is_offered_the_profile_first(self):
        body = self._page(self.APPLE)
        primary = body.split('class="btn"', 1)[1].split(">", 1)[0]
        self.assertIn(".mobileconfig", primary)

    def test_everything_else_is_offered_the_certificate_first(self):
        for agent in (self.ANDROID, self.WINDOWS, ""):
            with self.subTest(agent=agent[:24] or "no user agent"):
                body = self._page(agent)
                primary = body.split('class="btn"', 1)[1].split(">", 1)[0]
                self.assertIn("ca.crt", primary)

    def test_both_files_are_always_reachable_whatever_the_guess(self):
        # The sniff must never WITHHOLD. A misidentified device still has to be able
        # to get the file it needs without knowing that it was misidentified.
        for agent in (self.APPLE, self.ANDROID, self.WINDOWS, ""):
            with self.subTest(agent=agent[:24] or "no user agent"):
                body = self._page(agent)
                self.assertIn("/edge/trust/ca.crt", body)
                self.assertIn("/edge/trust/box-ca.mobileconfig", body)

    def test_every_platform_keeps_its_instructions_whatever_the_guess(self):
        for agent in (self.APPLE, self.ANDROID, self.WINDOWS, ""):
            with self.subTest(agent=agent[:24] or "no user agent"):
                body = self._page(agent)
                for needle in ("Windows", "Android", "iPhone"):
                    self.assertIn(needle, body)

    def test_windows_is_given_the_one_command_that_replaces_the_wizard(self):
        body = self._page(self.WINDOWS)
        self.assertIn("Import-Certificate", body)
        self.assertIn("Cert:\\LocalMachine\\Root", body)

    def test_the_other_platforms_commands_are_present_but_folded_away(self):
        # This used to assert Import-Certificate was ABSENT from an Apple
        # device's page, from when the Windows command was rendered only for
        # Windows. That rule contradicted this class's own docstring:
        # withholding a route on the strength of a user-agent string is exactly
        # the "sniffing that decides what a person is ALLOWED to see" the view
        # refuses to do. The person on a Mac setting up a Windows lab is real,
        # and a UA guess must never lock them out of what they came for.
        #
        # The rule is ORDER, which a wrong guess can only make inconvenient:
        # every platform's command is on the page, exactly one is unfolded.
        body = self._page(self.APPLE)
        self.assertIn("Import-Certificate", body)
        self.assertEqual(body.count('<details class="ins" open>'), 1)
        opened = body.split('<details class="ins" open>', 1)[1].split(
            "</summary>", 1
        )[0]
        self.assertIn("macOS", opened)

    def test_an_android_user_agent_is_not_mistaken_for_a_desktop(self):
        # It says "Linux" and it says "Chrome"; the ordering of the token table is
        # what keeps it out of the wrong branch.
        request = RequestFactory().get("/edge/trust/", HTTP_USER_AGENT=self.ANDROID)
        self.assertEqual(_device_hint(request), "android")

    def test_an_ipad_claiming_to_be_a_macintosh_still_gets_the_profile(self):
        # Safari on iPadOS has reported itself as a Macintosh since iPadOS 13. That
        # is the right answer here anyway -- a Mac installs the same profile -- but
        # only because the apple branch is checked before anything else.
        ipad = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
        request = RequestFactory().get("/edge/trust/", HTTP_USER_AGENT=ipad)
        self.assertEqual(_device_hint(request), "apple")


class BothRunbooksCarryTheManagedRouteTests(SimpleTestCase):
    """A school that can push should never read the per-device steps.

    The wizard's copy is the one printed and read weeks later by somebody who cannot
    check it against a running box, so it cannot be the copy that omits the route
    which makes the whole chore unnecessary.
    """

    def _generated(self):
        from apps.schools import edge_onboarding

        return edge_onboarding._runbook(
            mode=edge_tls.MODE_SELF_SIGNED,
            dns_names=["gilead-tech.local"],
            ip_addresses=["10.10.20.137"],
            mobility=edge_onboarding.MOVE_NEVER,
            web_port="10000",
        )

    def test_the_console_push_is_offered_before_the_per_device_walk(self):
        # ORDER, not presence. Reading "install it on every device" first is exactly
        # how somebody spends an afternoon walking a building doing by hand what one
        # console push would have done for the whole fleet in a minute.
        steps = self._generated()
        managed = next(i for i, s in enumerate(steps) if "--export-mdm" in s)
        per_device = next(
            i for i, s in enumerate(steps) if "install it on every device" in s
        )
        self.assertLess(managed, per_device)

    def test_the_generated_runbook_says_how_to_confirm_before_doing_thirty(self):
        joined = "\n".join(self._generated())
        self.assertIn("Check it worked", joined)
        self.assertIn("one mistake and thirty", joined)

    def test_the_generated_runbook_is_honest_about_a_negative_answer(self):
        # The same discipline the page keeps: a failed handshake is not proof the CA
        # is missing, and a runbook that says it is sends people to reinstall.
        joined = "\n".join(self._generated())
        self.assertIn("OR the box is not answering", joined)

    def test_the_tls_runbook_documents_the_export_and_the_check(self):
        text = (
            Path(settings.BASE_DIR)
            .joinpath("docs", "EDGE_TLS_RUNBOOK.md")
            .read_text(encoding="utf-8")
        )
        self.assertIn("--export-mdm", text)
        self.assertIn("box-ca.mobileconfig", text)
        self.assertIn("android-policy.json", text)
        self.assertIn("5d.", text)

    def test_the_tls_runbook_explains_why_the_identifiers_are_stable(self):
        # If this reasoning is not written down, the next person "tidies" it into a
        # random UUID and every push silently adds a trust anchor to every device.
        text = (
            Path(settings.BASE_DIR)
            .joinpath("docs", "EDGE_TLS_RUNBOOK.md")
            .read_text(encoding="utf-8")
        )
        self.assertIn("PayloadIdentifier", text)
        self.assertIn("Random UUIDs", text)


class TheConsoleCanDoTheComparingTests(SimpleTestCase):
    """The one step on that page that is still a person reading 64 hex characters.

    It is also the step everything else rests on: over plain http anyone on the
    network can answer in the box's place, and a certificate authority you install
    can vouch for any site. What people actually do is check the first four
    characters and the last four -- which is exactly the shape an attacker would
    choose. So the console will compare it instead.

    The judgement stays with the operator. Only the character-by-character reading
    is taken off them.
    """

    def _issue(self, directory):
        edge_tls.issue_self_signed(
            directory, dns_names=["gilead-tech.local"], ip_addresses=[], days=825
        )
        return edge_tls.inspect_certificate(os.path.join(directory, "ca.crt")).fingerprint

    def _run(self, value, directory):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        with mock.patch.dict(os.environ, {edge_tls.ENV_DIR: directory}, clear=False):
            call_command("edge_tls", "--verify-fingerprint", value, stdout=out)
        return out.getvalue()

    def _expect_refusal(self, value, directory):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with mock.patch.dict(os.environ, {edge_tls.ENV_DIR: directory}, clear=False):
            with self.assertRaises(CommandError) as caught:
                call_command("edge_tls", "--verify-fingerprint", value)
        return str(caught.exception)

    def test_the_box_says_match_for_its_own_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            fingerprint = self._issue(directory)
            self.assertIn("MATCH", self._run(fingerprint, directory))

    def test_it_accepts_the_spelling_a_clipboard_actually_produces(self):
        # The page shows colons; a console log might not; somebody will lower-case it
        # on the way through a chat message. All three are the same digest, and a
        # tool that rejected two of them would just be trained around.
        with tempfile.TemporaryDirectory() as directory:
            fingerprint = self._issue(directory)
            for spelling in (
                fingerprint,
                fingerprint.replace(":", ""),
                fingerprint.lower(),
                fingerprint.replace(":", " "),
            ):
                with self.subTest(spelling=spelling[:24]):
                    self.assertIn("MATCH", self._run(spelling, directory))

    def test_a_different_certificate_authority_fails_loudly(self):
        with tempfile.TemporaryDirectory() as directory:
            self._issue(directory)
            message = self._expect_refusal("AB:" * 31 + "AB", directory)
        self.assertIn("DOES NOT MATCH", message)
        self.assertIn("Do NOT install", message)

    def test_a_mismatch_exits_non_zero_so_a_script_can_branch_on_it(self):
        # CommandError is how a management command exits non-zero. A printed warning
        # would be skimmed; a red exit is not.
        from django.core.management.base import CommandError

        with tempfile.TemporaryDirectory() as directory:
            self._issue(directory)
            with self.assertRaises(CommandError):
                self._run("AB:" * 31 + "AB", directory)

    def test_a_partial_fingerprint_is_refused_rather_than_compared(self):
        # THE test here. Comparing a prefix passes on any certificate that merely
        # starts the same way -- which is the precise mistake this flag exists to
        # remove, so accepting one would make the tool an accomplice to it.
        with tempfile.TemporaryDirectory() as directory:
            fingerprint = self._issue(directory)
            message = self._expect_refusal(fingerprint[:20], directory)
        self.assertIn("Refusing to compare part", message)

    def test_a_box_with_no_authority_says_so_instead_of_answering(self):
        with tempfile.TemporaryDirectory() as empty:
            message = self._expect_refusal("AB:" * 31 + "AB", empty)
        self.assertIn("no readable certificate authority", message)

    def test_the_page_tells_people_the_flag_is_there(self):
        # A tool nobody is told about is a tool nobody uses, and the place to say so
        # is beside the fingerprint it checks.
        with tempfile.TemporaryDirectory() as directory:
            fingerprint = self._issue(directory)
            env = {
                edge_tls.ENV_DIR: directory,
                edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
            }
            with override_settings(**BOX), mock.patch.dict(
                os.environ, env, clear=False
            ):
                request = RequestFactory().get(
                    "/edge/trust/", HTTP_HOST="gilead-tech.local"
                )
                request.csp_nonce = "n"
                body = edge_trust_page(request).content.decode("utf-8")
        self.assertIn("--verify-fingerprint", body)
        self.assertIn(fingerprint, body)


class TheCommandCannotInstallTheWrongThingTests(SimpleTestCase):
    """Step 3 became a paste. A paste is only better if it cannot install anything else.

    Everything here is about the two ways handing over a command could be WORSE than
    the six screens of UI it replaces: installing a certificate nobody checked, or
    executing something the network handed us. Both are sealed rather than described,
    because both are the kind of thing a later "simplification" removes without
    noticing it was load-bearing.
    """

    FP = (
        "F5:7D:37:13:77:53:40:C1:FB:56:17:82:27:D4:0C:6B:"
        "55:49:1C:C6:BC:3E:39:54:B4:0D:7E:2C:5D:BF:8E:68"
    )
    URL = "http://10.10.20.137:10000/edge/trust/ca.crt"

    def _commands(self, url=None, fingerprint=None):
        return edge_tls.install_commands(
            self.URL if url is None else url,
            self.FP if fingerprint is None else fingerprint,
        )

    # -- the digest, in the one spelling a machine can compare ---------------------

    def test_the_two_spellings_of_one_fingerprint_are_reconciled_in_one_place(self):
        # openssl prints colons and .NET does not. They are the same digest, which is
        # exactly why a person asked to compare across the difference stops reading.
        self.assertEqual(
            edge_tls.compact_fingerprint(self.FP),
            "F57D3713775340C1FB56178227D40C6B55491CC6BC3E3954B40D7E2C5DBF8E68",
        )

    def test_it_survives_the_shell_and_clipboard_a_value_may_arrive_through(self):
        for spelling in (
            "f5:7d:37:13",
            "F5 7D 37 13",
            "F5-7D-37-13",
            " F5:7D:37:13 ",
        ):
            with self.subTest(spelling=spelling):
                self.assertEqual(edge_tls.compact_fingerprint(spelling), "F57D3713")

    def test_nothing_at_all_is_not_a_fingerprint(self):
        for empty in ("", None, "   "):
            with self.subTest(empty=empty):
                self.assertEqual(edge_tls.compact_fingerprint(empty), "")

    # -- the refusals, which are the whole point ----------------------------------

    def test_no_fingerprint_means_no_command(self):
        # A command without one installs whatever it is handed, which is strictly
        # worse than the manual steps it replaces: those at least end with a person
        # looking at a certificate.
        self.assertEqual(self._commands(fingerprint=""), ())

    def test_a_truncated_fingerprint_means_no_command(self):
        # grep matches a PREFIX. A half-length fingerprint would compare equal to any
        # certificate that happens to start the same way -- a check that passes when
        # it should not, which is the only kind that is worse than no check.
        self.assertEqual(self._commands(fingerprint=self.FP[:20]), ())

    def test_no_url_means_no_command(self):
        self.assertEqual(self._commands(url="  "), ())

    # -- what the command does, and refuses to do ---------------------------------

    def test_every_platform_pins_the_full_fingerprint(self):
        want = edge_tls.compact_fingerprint(self.FP)
        commands = self._commands()
        self.assertEqual({c.platform for c in commands}, {"windows", "macos", "linux"})
        for entry in commands:
            with self.subTest(platform=entry.platform):
                self.assertIn(want, entry.command)
                self.assertIn(self.URL, entry.command)

    def test_nothing_fetched_is_ever_executed(self):
        # THE seal. This page is served over plain http on a school LAN -- that is
        # load-bearing, not an oversight -- so a command that ran whatever the box
        # sent back would promote a LAN attacker from "your trust store" to "your
        # machine". Installing a fingerprint-checked certificate cannot do that
        # however the page is answered; piping a download into a shell can.
        forbidden = (
            "| bash",
            "|bash",
            "| sh",
            "|sh",
            "invoke-expression",
            "iex ",
            "eval ",
            "wget -o -",
            "curl -s |",
        )
        for entry in self._commands():
            body = entry.command.lower()
            for token in forbidden:
                with self.subTest(platform=entry.platform, token=token):
                    self.assertNotIn(token, body)

    def test_the_download_goes_to_a_file_rather_than_a_pipe(self):
        commands = {c.platform: c.command for c in self._commands()}
        self.assertIn("-OutFile", commands["windows"])
        self.assertIn("-o /tmp/box-ca.crt", commands["macos"])
        self.assertIn("-o /tmp/box-ca.crt", commands["linux"])

    def test_the_windows_branch_is_one_line_because_a_console_eats_the_else(self):
        # Pasted into a console, an `if` block that ends at a newline is executed
        # before the `else` arrives, and the operator gets a parse error on a line
        # they did not write. Cost of getting this wrong: the command "does nothing"
        # and the person concludes the box is broken.
        windows = {c.platform: c.command for c in self._commands()}["windows"]
        branch = [line for line in windows.splitlines() if line.startswith("if (")]
        self.assertEqual(len(branch), 1, windows)
        self.assertIn("} else {", branch[0])
        self.assertIn("Import-Certificate", branch[0])

    def test_windows_targets_the_machine_store_not_the_user_store(self):
        # The single commonest way this fails: the user store is where a double-click
        # puts it and where Chrome and Edge do not look.
        windows = {c.platform: c.command for c in self._commands()}["windows"]
        self.assertIn("Cert:\\LocalMachine\\Root", windows)
        self.assertNotIn("CurrentUser", windows)

    def test_the_posix_check_matches_what_openssl_actually_prints(self):
        # Reproduces the pipeline the command runs -- `openssl x509 -fingerprint
        # -sha256 | tr -d ': ' | grep -qi <want>` -- against the exact line openssl
        # emits, rather than asserting the string is present somewhere.
        want = edge_tls.compact_fingerprint(self.FP)
        printed = f"sha256 Fingerprint={self.FP}"
        stripped = printed.replace(":", "").replace(" ", "").upper()
        self.assertIn(want, stripped)

    def test_the_posix_check_does_not_match_a_different_certificate(self):
        # Proving a detector before believing it: a check that matches everything
        # reports success on the wrong CA, which is the failure it exists to catch.
        want = edge_tls.compact_fingerprint(self.FP)
        other = "0" * 64
        printed = f"sha256 Fingerprint={':'.join(other[i:i + 2] for i in range(0, 64, 2))}"
        stripped = printed.replace(":", "").replace(" ", "").upper()
        self.assertNotIn(want, stripped)

    def test_every_route_says_what_it_does_not_cover(self):
        # Firefox keeps its own store everywhere and Chrome does on Linux. A browser
        # that still warns after this succeeded is not evidence that it failed -- and
        # somebody who is not told that spends the afternoon re-installing.
        for entry in self._commands():
            with self.subTest(platform=entry.platform):
                self.assertTrue(entry.caveat.strip())
                self.assertIn("Firefox", entry.caveat)

    def test_two_different_boxes_produce_two_different_commands(self):
        # Tenant-wide, not Gilead-shaped: nothing here is derived from a school name,
        # and a second box's command must pin the second box's certificate.
        other = "AB:" * 31 + "AB"
        mine = {c.platform: c.command for c in self._commands()}
        theirs = {c.platform: c.command for c in self._commands(fingerprint=other)}
        for platform in mine:
            with self.subTest(platform=platform):
                self.assertNotEqual(mine[platform], theirs[platform])


class ThePageHandsOverTheCommandTests(TenantUrlconfMixin, SimpleTestCase):
    """The device reading the page is offered its own command, opened."""

    APPLE = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/125"
    WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125"

    def _page(self, agent="", corrupt_ca=False):
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory,
                dns_names=["gilead-tech.local"],
                ip_addresses=[],
                days=825,
            )
            ca_path = os.path.join(directory, "ca.crt")
            fingerprint = edge_tls.inspect_certificate(ca_path).fingerprint
            if corrupt_ca:
                with open(ca_path, "wb") as handle:
                    handle.write(b"-----BEGIN CERTIFICATE-----\nnope\n")
            env = {
                edge_tls.ENV_DIR: directory,
                edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
            }
            with override_settings(**BOX), mock.patch.dict(
                os.environ, env, clear=False
            ):
                request = RequestFactory().get(
                    "/edge/trust/",
                    HTTP_HOST="gilead-tech.local:10000",
                    **({"HTTP_USER_AGENT": agent} if agent else {}),
                )
                request.csp_nonce = "test-nonce-abc"
                body = edge_trust_page(request).content.decode("utf-8")
        return body, fingerprint

    def test_the_command_carries_this_box_and_not_a_placeholder(self):
        body, fingerprint = self._page(self.WINDOWS)
        self.assertIn(edge_tls.compact_fingerprint(fingerprint), body)
        self.assertIn("http://gilead-tech.local:10000/edge/trust/ca.crt", body)

    def test_a_windows_device_finds_its_own_route_already_open(self):
        body, _ = self._page(self.WINDOWS)
        opened = re.findall(r'<details class="ins"( open)?>\s*<summary>.*?</strong>', body)
        self.assertTrue(opened, body[:400])
        self.assertEqual(opened[0], " open", "the first route shown must be this one")
        self.assertIn("Import-Certificate", body)

    def test_a_mac_finds_the_mac_route_open(self):
        body, _ = self._page(self.APPLE)
        first = body.split('<details class="ins"', 1)[1].split("</summary>", 1)[0]
        self.assertIn(" open", first)
        self.assertIn("macOS", first)

    def test_a_device_with_no_shell_has_nothing_opened_for_it(self):
        # Android has no terminal to paste into, so opening a command there would be
        # a screen of text that cannot be acted on. Every route stays reachable.
        body, _ = self._page(self.ANDROID)
        self.assertIn('<details class="ins">', body)
        self.assertNotIn('<details class="ins" open>', body)

    def test_an_unknown_device_is_told_nothing_it_cannot_use(self):
        body, _ = self._page()
        self.assertIn('<details class="ins">', body)
        self.assertNotIn('<details class="ins" open>', body)

    def test_the_by_hand_steps_did_not_go_away(self):
        # The command is the fast route, not the only one. A locked-down machine, a
        # phone, and anyone who would rather see the dialog all still need these.
        body, _ = self._page(self.WINDOWS)
        for prose in (
            "Trusted Root",
            "Certificate Trust Settings",
            "install from storage",
        ):
            with self.subTest(prose=prose):
                self.assertIn(prose, body)

    def test_a_box_whose_ca_cannot_be_read_offers_no_command_at_all(self):
        # And still renders. An unreadable CA is its own state: there is no
        # fingerprint to pin a command to, so there is no command -- rather than a
        # command that would install anything it was given.
        body, _ = self._page(self.WINDOWS, corrupt_ca=True)
        self.assertNotIn('<details class="ins"', body)
        self.assertIn("cannot be read", body)

    def test_the_copy_helper_is_not_the_clipboard_api(self):
        # navigator.clipboard.writeText is withheld outside a secure context, and
        # this page is plain http BY DESIGN -- so a copy button here would be a
        # button that does nothing on the one page that cannot be served any other
        # way. Selecting the text leaves the copy to Ctrl-C.
        body, _ = self._page(self.WINDOWS)
        self.assertIn("selectNodeContents", body)
        # Comments stripped first. The block explains at length that it is NOT
        # navigator.clipboard.writeText, so asserting against the raw page would
        # trip on the reasoning rather than on the code -- which is a test that
        # fails for being well documented.
        directives = "\n".join(
            line
            for line in body.splitlines()
            if not line.strip().startswith("//")
        )
        self.assertNotIn("navigator.clipboard", directives)

    def test_every_script_on_the_page_carries_the_nonce(self):
        # CSP_ENFORCE defaults to 1 and script-src is 'self' with a per-request
        # nonce. This page renders with a plain dict so no context processor runs,
        # so the nonce is passed explicitly -- and a second <script> added later is
        # exactly where that gets forgotten. Silent failure: the block is dropped
        # and the page looks fine.
        body, _ = self._page(self.WINDOWS)
        scripts = re.findall(r"<script([^>]*)>", body)
        self.assertGreaterEqual(len(scripts), 2)
        for attributes in scripts:
            with self.subTest(attributes=attributes):
                self.assertIn('nonce="test-nonce-abc"', attributes)


class TheCheckNoLongerWaitsToBeAskedTests(TenantUrlconfMixin, SimpleTestCase):
    """A button is a thing to notice, and the person who needs it did not notice."""

    def _page(self):
        with tempfile.TemporaryDirectory() as directory:
            edge_tls.issue_self_signed(
                directory, dns_names=["gilead-tech.local"], ip_addresses=[], days=825
            )
            env = {
                edge_tls.ENV_DIR: directory,
                edge_tls.ENV_MODE: edge_tls.MODE_SELF_SIGNED,
            }
            with override_settings(**BOX), mock.patch.dict(
                os.environ, env, clear=False
            ):
                request = RequestFactory().get(
                    "/edge/trust/", HTTP_HOST="gilead-tech.local"
                )
                request.csp_nonce = "n"
                return edge_trust_page(request).content.decode("utf-8")

    def _verify_script(self, body):
        blocks = re.findall(r"<script[^>]*>(.*?)</script>", body, re.S)
        matching = [b for b in blocks if "rmc-verify" in b]
        self.assertEqual(len(matching), 1)
        return matching[0]

    def test_the_check_runs_without_being_asked(self):
        script = self._verify_script(self._page())
        self.assertIn("btn.addEventListener(\"click\", run);", script)
        self.assertRegex(script, r"\n\s*run\(\);", "the check must fire on load")

    def test_it_is_still_an_image_and_not_a_cross_origin_fetch(self):
        # Running on load makes this MORE important, not less: `connect-src 'self'`
        # would block a fetch to the https origin outright, and the page would then
        # report "not confirmed" about a device that trusts the box perfectly well --
        # now to every visitor, automatically, with nobody having pressed anything.
        script = self._verify_script(self._page())
        self.assertIn("new Image()", script)
        directives = "\n".join(
            line for line in script.splitlines() if not line.strip().startswith("//")
        )
        self.assertNotIn("fetch(", directives)

    def test_the_button_only_becomes_check_again_once_there_is_an_answer(self):
        # Relabelling in the markup would offer "Check again" to somebody who has not
        # been told anything yet.
        body = self._page()
        self.assertIn('id="rmc-msg-again"', body)
        button = body.split('id="rmc-verify"', 1)[1].split("</button>", 1)[0]
        self.assertNotIn("Check again", button)


class TheBootstrapStoppedAskingForThingsTests(SimpleTestCase):
    """Two hard stops removed, and neither of them by lowering the bar.

    The passphrase stop turned "run one command" back into "read the script, work out
    what it wants, invent a secret" -- and the secret invented at a console in a
    school office is either weak or lost by the time the box needs restoring. The
    payload export was a second command nobody remembered existed, which is how a
    school that could have pushed the CA to every device from one console ended up
    walking the building instead.
    """

    def _script(self):
        return (
            Path(settings.BASE_DIR)
            .joinpath("deploy", "selfhost", "edge-bootstrap.sh")
            .read_text(encoding="utf-8")
        )

    def test_the_script_is_lf_only_because_a_cr_is_a_boot_failure(self):
        raw = (
            Path(settings.BASE_DIR)
            .joinpath("deploy", "selfhost", "edge-bootstrap.sh")
            .read_bytes()
        )
        self.assertNotIn(b"\r", raw, "a CR in this file is `\\r: command not found`")

    def test_a_missing_passphrase_is_no_longer_a_dead_stop(self):
        script = self._script()
        self.assertIn("new_passphrase()", script)
        self.assertNotIn("Set RMC_EDGE_TLS_CA_PASSPHRASE in your shell first", script)

    def test_a_generated_passphrase_is_reused_rather_than_replaced(self):
        # A second passphrase would re-encrypt the bundle and silently strand
        # whatever copy is already off the box.
        script = self._script()
        self.assertIn('if [ -s "$PASSPHRASE_FILE" ]; then', script)
        self.assertIn('tr -d \'\\r\\n\' < "$PASSPHRASE_FILE"', script)

    def test_it_is_written_owner_only(self):
        self.assertIn("umask 077", self._script())

    def test_an_operator_supplied_passphrase_still_wins(self):
        script = self._script()
        self.assertIn('if [ -z "${RMC_EDGE_TLS_CA_PASSPHRASE:-}" ]; then', script)

    def test_where_it_is_written_is_overridable(self):
        self.assertIn('${RMC_EDGE_CA_PASSPHRASE_FILE:-', self._script())

    def test_the_closing_notes_admit_the_two_files_start_out_together(self):
        # They do, and pretending otherwise is worse than the arrangement itself:
        # together in one place the encryption bought you nothing.
        script = self._script()
        self.assertIn("$PASSPHRASE_FILE", script)
        self.assertIn("so they stop sitting together", script)

    def test_the_console_payloads_are_written_every_run(self):
        script = self._script()
        self.assertIn("--export-mdm", script)
        self.assertIn("Management-console payloads", script)

    def test_a_failed_payload_export_warns_and_does_not_stop_the_box(self):
        # A box whose TLS is correct is not less correct because a folder could not
        # be copied off it. This is the same rule as a boot helper never failing the
        # boot, and it is the rule this file gets wrong most easily.
        script = self._script()
        section = script.split("Management-console payloads", 1)[1].split("# --- 6.", 1)[0]
        self.assertIn("warn ", section)
        self.assertNotIn("die ", section)

    def test_the_payloads_are_staged_rather_than_copied_onto_themselves(self):
        # `docker compose cp` of a directory copies INTO an existing target, so a
        # second run would leave $OUT_DIR/mdm/mdm and a stale copy above it.
        script = self._script()
        self.assertIn('MDM_TMP="$(mktemp -d)"', script)
        self.assertIn('mv "$MDM_TMP/mdm" "$OUT_DIR/mdm"', script)
        self.assertNotIn('cp web:/app/var/mdm "$OUT_DIR/mdm"', script)

    def test_the_temporary_directory_is_cleaned_up_however_it_exits(self):
        self.assertIn('rm -rf "$MDM_TMP"', self._script())

    def test_the_script_still_parses(self):
        # Content assertions above prove the words are there; only bash proves the
        # file is a program. Skipped rather than faked where bash is absent.
        import shutil
        import subprocess

        bash = shutil.which("bash")
        if not bash:
            self.skipTest("no bash on PATH")
        path = Path(settings.BASE_DIR).joinpath("deploy", "selfhost", "edge-bootstrap.sh")
        result = subprocess.run(
            [bash, "-n", str(path)], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class TheWizardLeadsWithTheOneCommandTests(SimpleTestCase):
    """The generated runbook is read top to bottom by somebody standing at a box.

    Whichever route is first is the route that gets taken, so the automated one has
    to be first -- and the hand-run commands have to survive underneath it, because a
    box whose HOST has no shell still has to be brought up somehow, and a step nobody
    can read is a step nobody can debug the day the script refuses.
    """

    def _steps(self, mode=edge_tls.MODE_SELF_SIGNED):
        from apps.schools import edge_onboarding

        return edge_onboarding._runbook(
            mode=mode,
            dns_names=["gilead-tech.local"],
            ip_addresses=["10.10.20.137"],
            mobility=edge_onboarding.MOVE_NEVER,
            web_port="10000",
        )

    def _index(self, steps, needle):
        return next(i for i, step in enumerate(steps) if needle in step)

    def test_the_script_is_offered_before_any_command_it_replaces(self):
        steps = self._steps()
        script = self._index(steps, "edge-bootstrap.sh")
        for later in ("--issue-selfsigned", "--export-ca", "--print-caddyfile"):
            with self.subTest(later=later):
                self.assertLess(script, self._index(steps, later))

    def test_the_hand_run_sequence_is_still_there_and_still_in_order(self):
        steps = self._steps()
        self.assertLess(
            self._index(steps, "--issue-selfsigned"),
            self._index(steps, "--print-caddyfile"),
            "rendering the terminator config before the certificate exists emits "
            "`tls internal`, and the CA you then install matches nothing",
        )

    def test_it_says_it_is_safe_to_run_again(self):
        # Operators do not re-run something that might do damage, so a script that is
        # idempotent but does not say so gets run once and then worked around.
        step = self._steps()[self._index(self._steps(), "edge-bootstrap.sh")]
        self.assertIn("again", step)

    def test_it_says_there_is_nothing_to_set_up_first(self):
        step = self._steps()[self._index(self._steps(), "edge-bootstrap.sh")]
        self.assertIn("passphrase", step)

    def test_a_mode_the_script_was_not_written_for_is_not_offered_it(self):
        # The script mints a box CA and backs it up. Pointing an acme box at it would
        # be a command that fails for a reason the runbook never mentions.
        for mode in (edge_tls.MODE_OFF, edge_tls.MODE_ACME, edge_tls.MODE_PROVIDED):
            with self.subTest(mode=mode):
                self.assertFalse(
                    any("edge-bootstrap.sh" in step for step in self._steps(mode))
                )

    def test_the_managed_route_no_longer_asks_for_a_command_first(self):
        steps = self._steps()
        managed = steps[self._index(steps, "manages its devices")]
        self.assertIn("mdm/", managed)
        self.assertIn("already wrote", managed)

    def test_the_enrolment_step_mentions_the_one_paste(self):
        steps = self._steps()
        enrol = steps[self._index(steps, edge_tls.TRUST_ENROLMENT_PATH)]
        self.assertIn("one paste", enrol)
        self.assertIn("ONLY on a match", enrol)

    def test_the_confirmation_step_says_it_runs_itself(self):
        steps = self._steps()
        confirm = steps[self._index(steps, "Check it worked")]
        self.assertIn("runs by itself", confirm)
        # Still honest about a negative answer -- automating the check must not turn
        # "we could not confirm" into "the certificate is missing".
        self.assertIn("OR the box is not answering", confirm)


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

    def test_the_generated_passphrase_cannot_be_committed(self):
        # The bootstrap GENERATES this now rather than making the operator invent
        # one, so it appears on far more boxes than it used to -- and it is the one
        # file that, sitting beside box-ca-bundle.p12 in a public place, makes the
        # encryption on that bundle worth nothing.
        ignored = self._repo_file(".gitignore").read_text(encoding="utf-8")
        self.assertIn("box-ca-passphrase.txt", ignored)

    def test_the_whole_console_payload_folder_is_ignored(self):
        # Written on EVERY bootstrap run now, not only when somebody remembers the
        # command, so it turns up beside a checkout far more often -- README and all,
        # and the README names the fingerprint.
        ignored = self._repo_file(".gitignore").read_text(encoding="utf-8")
        self.assertIn("mdm/", ignored)

    def test_the_management_export_cannot_be_committed_either(self):
        # `--export-mdm` produces a folder in a hurry, and the obvious place to put
        # it is wherever you are standing -- which on a box is the checkout.
        ignored = self._repo_file(".gitignore").read_text(encoding="utf-8")
        self.assertIn("box-ca.mobileconfig", ignored)
        self.assertIn("android-policy.json", ignored)

    def test_box_identity_handed_out_at_onboarding_is_ignored(self):
        # Same exposure class as the .p12: these name and authenticate ONE box, and
        # five of them were found sitting untracked in a live box's checkout, none
        # of them matched by any rule at the time.
        ignored = self._repo_file(".gitignore").read_text(encoding="utf-8")
        for pattern in ("*.rmcidentity", "*.rmcbundle", "*.b64"):
            self.assertIn(pattern, ignored)


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
