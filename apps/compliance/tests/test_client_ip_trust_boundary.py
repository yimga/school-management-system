"""Every IP-bearing compliance control must read a TRUSTED ``X-Forwarded-For`` hop.

``X-Forwarded-For`` is client-controlled to the LEFT: a reverse proxy appends its
own observation to the RIGHT of whatever the client sent. Taking ``[0]`` therefore
reads a value the attacker chose, which made the auditor geo-fence, the
IPAccessRule/CountryAccessRule perimeter and every AccessLog/AuditLog source-IP
column trivially forgeable. ``apps.api.rate_limit.client_ip`` is the repo's
trusted-proxy-depth parse (``XFF[-RATE_LIMIT_TRUSTED_PROXY_COUNT]``); these tests
pin every compliance IP reader onto it.

The header shape used throughout is ``"<forged>, <real>"`` with
``RATE_LIMIT_TRUSTED_PROXY_COUNT=1`` — one load balancer, which appended the real
peer address on the right. The leftmost entry is the attacker's invention.
"""

from django.test import RequestFactory, TestCase, override_settings

from apps.compliance import auditor_access
from apps.compliance.access_control import check_request_access
from apps.compliance.models import AuditorAccessLog
from apps.compliance.models_audit import IPAccessRule
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig

FORGED = "198.51.100.42"
REAL = "203.0.113.9"
SPOOFED_XFF = f"{FORGED}, {REAL}"


@override_settings(RATE_LIMIT_TRUSTED_PROXY_COUNT=1)
class CompliancePrimitiveClientIPTests(TestCase):
    """The bare IP readers each control depends on."""

    def setUp(self):
        self.factory = RequestFactory()

    def _request(self):
        return self.factory.get("/", HTTP_X_FORWARDED_FOR=SPOOFED_XFF, REMOTE_ADDR="10.0.0.1")

    def test_views_auditor_client_ip_ignores_forged_left_hop(self):
        from apps.compliance.views_auditor import _client_ip

        self.assertEqual(_client_ip(self._request()), REAL)

    def test_decorators_client_ip_ignores_forged_left_hop(self):
        from apps.compliance.decorators import _client_ip

        self.assertEqual(_client_ip(self._request()), REAL)

    def test_signals_client_ip_ignores_forged_left_hop(self):
        from apps.compliance.signals import _client_ip

        self.assertEqual(_client_ip(self._request()), REAL)

    def test_middleware_ip_readers_ignore_forged_left_hop(self):
        from apps.compliance.middleware import (
            AccessControlMiddleware,
            AuditLoggingMiddleware,
            IPCountryAccessMiddleware,
        )

        for cls in (
            AuditLoggingMiddleware,
            AccessControlMiddleware,
            IPCountryAccessMiddleware,
        ):
            with self.subTest(middleware=cls.__name__):
                self.assertEqual(cls._get_ip_address(self._request()), REAL)

    def test_readers_still_fall_back_to_remote_addr(self):
        """No XFF at all must keep working — the proxy-less/LAN deployment."""
        from apps.compliance.views_auditor import _client_ip

        request = self.factory.get("/", REMOTE_ADDR=REAL)
        self.assertEqual(_client_ip(request), REAL)


@override_settings(RATE_LIMIT_TRUSTED_PROXY_COUNT=1)
class AuditorGeofenceSpoofingTests(TestCase):
    """AuditorAccessGrant.ip_allowlist is the whole geo-fence on a public link."""

    def setUp(self):
        self.factory = RequestFactory()
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            slug="auditor-xff-school",
            subdomain="auditor-xff-school",
            name="Auditor XFF School",
            default_region=self.region,
            timezone=self.region.timezone,
        )

    def _grant(self):
        # Allowlist covers FORGED but NOT REAL, so the two IPs decide the outcome.
        return auditor_access.create_grant(
            school_id=self.school.id, ip_allowlist=["198.51.100.0/24"]
        )

    def test_on_net_request_is_served(self):
        """Reached-the-code guard: the token, grant and roster path all work.

        Without this, the denial assertion below could pass because the link was
        broken rather than because the geo-fence held.
        """
        from apps.compliance.views_auditor import auditor_inspect

        _grant, token = self._grant()
        response = auditor_inspect(
            self.factory.get(
                f"/compliance/auditor/inspect/?token={token}&format=json",
                HTTP_X_FORWARDED_FOR=f"10.0.0.5, {FORGED}",
            )
        )
        self.assertEqual(response.status_code, 200)

    def test_forged_left_hop_does_not_satisfy_the_geofence(self):
        from apps.compliance.views_auditor import auditor_inspect

        grant, token = self._grant()
        response = auditor_inspect(
            self.factory.get(
                f"/compliance/auditor/inspect/?token={token}&format=json",
                HTTP_X_FORWARDED_FOR=SPOOFED_XFF,
                REMOTE_ADDR="10.0.0.1",
            )
        )
        self.assertEqual(
            response.status_code,
            403,
            "an off-net client must not reach the roster by forging the left XFF hop",
        )
        log = AuditorAccessLog.objects.get(grant=grant)
        self.assertFalse(log.allowed)
        self.assertEqual(log.denied_reason, "ip-not-in-allowlist")
        # The inspection trail must record where the request really came from.
        self.assertEqual(str(log.ip_address), REAL)


@override_settings(RATE_LIMIT_TRUSTED_PROXY_COUNT=1)
class IPRulePerimeterSpoofingTests(TestCase):
    """IPAccessRule DENY must not be escapable by inventing a left XFF hop."""

    def setUp(self):
        self.factory = RequestFactory()
        IPAccessRule.objects.create(
            rule_type=IPAccessRule.RuleType.DENY,
            ip_address=REAL,
            is_active=True,
        )

    def test_banned_ip_is_blocked_without_a_proxy_header(self):
        """Reached-the-code guard: the DENY rule is live and evaluated."""
        request = self.factory.get("/", REMOTE_ADDR=REAL)
        is_allowed, reason = check_request_access(request)
        self.assertFalse(is_allowed)
        self.assertIn("blocked", reason.lower())

    def test_banned_ip_cannot_escape_by_prepending_a_clean_hop(self):
        request = self.factory.get(
            "/", HTTP_X_FORWARDED_FOR=f"8.8.8.8, {REAL}", REMOTE_ADDR="10.0.0.1"
        )
        is_allowed, reason = check_request_access(request)
        self.assertFalse(
            is_allowed,
            "a denied client must not pass by prepending an unbanned IP to X-Forwarded-For",
        )
        self.assertIn("blocked", reason.lower())

    def test_allowed_ip_from_the_trusted_hop_still_passes(self):
        """The proxy's own appended entry is the one that must be honoured."""
        request = self.factory.get(
            "/", HTTP_X_FORWARDED_FOR=f"{REAL}, 8.8.8.8", REMOTE_ADDR="10.0.0.1"
        )
        is_allowed, _reason = check_request_access(request)
        self.assertTrue(is_allowed)
