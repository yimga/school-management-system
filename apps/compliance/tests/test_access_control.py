"""
Tests for IP and country-based access control.
"""

from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from apps.compliance.models_audit import IPAccessRule, CountryAccessRule
from apps.compliance.access_control import (
    check_ip_access,
    check_country_access,
    check_request_access,
)

User = get_user_model()


class IPAccessControlTestCase(TestCase):
    """Test IP-based access control."""

    def setUp(self):
        """Create test IP rules."""
        self.factory = RequestFactory()

    def test_no_rules_allows_all(self):
        """Test that with no rules, all IPs are allowed."""
        is_allowed, reason = check_ip_access("192.168.1.1")
        self.assertTrue(is_allowed)
        self.assertIn("No restrictions", reason)

    def test_deny_rule_blocks_ip(self):
        """Test that deny rule blocks specific IP."""
        IPAccessRule.objects.create(
            rule_type=IPAccessRule.RuleType.DENY,
            ip_address="192.168.1.100",
            is_active=True,
            description="Test block",
        )

        # Blocked IP
        is_allowed, reason = check_ip_access("192.168.1.100")
        self.assertFalse(is_allowed)
        self.assertIn("blocked", reason.lower())

        # Allowed IP
        is_allowed, reason = check_ip_access("192.168.1.101")
        self.assertTrue(is_allowed)

    def test_deny_rule_cidr_range(self):
        """Test that deny rule works with CIDR range."""
        IPAccessRule.objects.create(
            rule_type=IPAccessRule.RuleType.DENY,
            ip_address="192.168.1.0/24",
            is_active=True,
            description="Block subnet",
        )

        # IPs within range should be blocked
        is_allowed, _ = check_ip_access("192.168.1.1")
        self.assertFalse(is_allowed)

        is_allowed, _ = check_ip_access("192.168.1.255")
        self.assertFalse(is_allowed)

        # IP outside range should be allowed
        is_allowed, _ = check_ip_access("192.168.2.1")
        self.assertTrue(is_allowed)

    def test_allow_whitelist(self):
        """Test that allow rules create a whitelist."""
        # Create allow rules for specific IPs
        IPAccessRule.objects.create(
            rule_type=IPAccessRule.RuleType.ALLOW,
            ip_address="192.168.1.100",
            is_active=True,
            description="Allowed IP",
        )
        IPAccessRule.objects.create(
            rule_type=IPAccessRule.RuleType.ALLOW,
            ip_address="10.0.0.0/8",
            is_active=True,
            description="Allowed internal network",
        )

        # Whitelisted IP should be allowed
        is_allowed, _ = check_ip_access("192.168.1.100")
        self.assertTrue(is_allowed)

        is_allowed, _ = check_ip_access("10.0.5.5")
        self.assertTrue(is_allowed)

        # Non-whitelisted IP should be blocked
        is_allowed, reason = check_ip_access("192.168.1.101")
        self.assertFalse(is_allowed)
        self.assertIn("not in allow list", reason.lower())

    def test_deny_takes_precedence(self):
        """Test that deny rules take precedence over allow rules."""
        # Create allow rule
        IPAccessRule.objects.create(
            rule_type=IPAccessRule.RuleType.ALLOW,
            ip_address="192.168.1.0/24",
            is_active=True,
        )

        # Create deny rule for specific IP in that range
        IPAccessRule.objects.create(
            rule_type=IPAccessRule.RuleType.DENY,
            ip_address="192.168.1.100",
            is_active=True,
        )

        # Denied IP should be blocked even if in allow range
        is_allowed, reason = check_ip_access("192.168.1.100")
        self.assertFalse(is_allowed)
        self.assertIn("blocked", reason.lower())

        # Other IPs in range should be allowed
        is_allowed, _ = check_ip_access("192.168.1.101")
        self.assertTrue(is_allowed)

    def test_inactive_rules_ignored(self):
        """Test that inactive rules are not enforced."""
        IPAccessRule.objects.create(
            rule_type=IPAccessRule.RuleType.DENY,
            ip_address="192.168.1.100",
            is_active=False,  # Inactive
            description="Disabled rule",
        )

        # IP should be allowed since rule is inactive
        is_allowed, _ = check_ip_access("192.168.1.100")
        self.assertTrue(is_allowed)


class CountryAccessControlTestCase(TestCase):
    """Test country-based access control."""

    def test_no_rules_allows_all(self):
        """Test that with no rules, all countries are allowed."""
        is_allowed, reason = check_country_access("US")
        self.assertTrue(is_allowed)
        self.assertIn("restriction", reason.lower())

    def test_deny_rule_blocks_country(self):
        """Test that deny rule blocks specific country."""
        CountryAccessRule.objects.create(
            rule_type=CountryAccessRule.RuleType.DENY,
            country_code="CN",
            country_name="China",
            is_active=True,
        )

        # Blocked country
        is_allowed, reason = check_country_access("CN")
        self.assertFalse(is_allowed)
        self.assertIn("blocked", reason.lower())

        # Allowed country
        is_allowed, _ = check_country_access("US")
        self.assertTrue(is_allowed)

    def test_allow_whitelist(self):
        """Test that allow rules create a country whitelist."""
        CountryAccessRule.objects.create(
            rule_type=CountryAccessRule.RuleType.ALLOW,
            country_code="US",
            country_name="United States",
            is_active=True,
        )
        CountryAccessRule.objects.create(
            rule_type=CountryAccessRule.RuleType.ALLOW,
            country_code="CM",
            country_name="Cameroon",
            is_active=True,
        )

        # Whitelisted countries
        is_allowed, _ = check_country_access("US")
        self.assertTrue(is_allowed)

        is_allowed, _ = check_country_access("CM")
        self.assertTrue(is_allowed)

        # Non-whitelisted country
        is_allowed, reason = check_country_access("RU")
        self.assertFalse(is_allowed)
        self.assertIn("not in allow list", reason.lower())

    def test_case_insensitive_country_code(self):
        """Test that country code matching is case-insensitive."""
        CountryAccessRule.objects.create(
            rule_type=CountryAccessRule.RuleType.DENY, country_code="CN", is_active=True
        )

        # Test various cases
        is_allowed, _ = check_country_access("CN")
        self.assertFalse(is_allowed)

        is_allowed, _ = check_country_access("cn")
        self.assertFalse(is_allowed)

        is_allowed, _ = check_country_access("Cn")
        self.assertFalse(is_allowed)


class RequestAccessControlTestCase(TestCase):
    """Test request-level access control."""

    def setUp(self):
        """Create test request factory."""
        self.factory = RequestFactory()

    def test_request_access_with_ip_rules(self):
        """Test check_request_access with IP rules."""
        # Block specific IP
        IPAccessRule.objects.create(
            rule_type=IPAccessRule.RuleType.DENY,
            ip_address="192.168.1.100",
            is_active=True,
        )

        # Create request from blocked IP
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "192.168.1.100"

        is_allowed, reason = check_request_access(request)
        self.assertFalse(is_allowed)
        self.assertIn("blocked", reason.lower())

    def test_request_with_x_forwarded_for(self):
        """The TRUSTED X-Forwarded-For hop decides, not the leftmost one.

        X-Forwarded-For is client-controlled to the LEFT (a proxy appends its
        observation on the right), so this used to assert the leftmost entry --
        which meant any banned client could walk through the perimeter by
        prepending an unbanned address. The entry contributed by the outermost
        trusted proxy (RATE_LIMIT_TRUSTED_PROXY_COUNT hops from the right) is
        the one that is honoured. See test_client_ip_trust_boundary.py.
        """
        IPAccessRule.objects.create(
            rule_type=IPAccessRule.RuleType.DENY,
            ip_address="203.0.113.5",
            is_active=True,
        )

        # One proxy, which appended the real peer address 203.0.113.5 last.
        request = self.factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "192.168.1.1, 203.0.113.5"
        request.META["REMOTE_ADDR"] = "10.0.0.1"

        is_allowed, _ = check_request_access(request)
        self.assertFalse(is_allowed)

        # The same banned address in the forgeable LEFT position must not be
        # what the perimeter reads -- and must not let the client through.
        request = self.factory.get("/")
        request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.5, 198.51.100.7"
        request.META["REMOTE_ADDR"] = "10.0.0.1"

        is_allowed, _ = check_request_access(request)
        self.assertTrue(is_allowed)
