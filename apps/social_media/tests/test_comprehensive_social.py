"""
Emergency priority, token expiry isolation, and cross-tenant publish guards.
"""

from __future__ import annotations

import time
from datetime import timedelta
from unittest.mock import Mock, patch

from django.db import IntegrityError, transaction
from django.test import RequestFactory, SimpleTestCase, TestCase, tag
from django.utils import timezone
from rest_framework.test import force_authenticate

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.schools.rls_context import rls_bypass
from apps.siteconfig.models import RegionConfig
from apps.social_media.models import SocialMediaIntegration, SocialProvider
from apps.social_media.scope import SocialTenantScopeError, assert_integration_access
from apps.social_media.services import emergency, providers
from apps.social_media.services.aggregator import sync_integration_feed
from apps.social_media.services.emergency import saturate_standard_backlog


class EmergencyRouterTests(SimpleTestCase):
    def test_emergency_dispatch_completes_under_one_second(self):
        saturate_standard_backlog(10_000)
        integration = Mock()
        integration.id = "00000000-0000-0000-0000-000000000099"
        integration.school_id = None
        integration.school = None
        integration.provider = "x"
        integration.handle = "@corp"
        integration.encrypted_oauth_token = "tok"
        integration.token_expired = Mock(return_value=False)
        integration.append_audit = Mock()

        request = Mock()
        request.school = None
        request.user = Mock(is_authenticated=True, pk=1)

        row = Mock()
        row.id = "00000000-0000-0000-0000-000000000001"
        row.priority = 0
        row.save = Mock()

        with patch(
            "apps.social_media.services.emergency.publisher.enqueue_cross_post",
            return_value=[row],
        ):
            with patch(
                "apps.social_media.services.emergency.publisher.process_outbox_row",
                return_value={"ok": True},
            ):
                started = time.monotonic()
                result = emergency.route_emergency_broadcast(
                    request, body="Campus closed due to weather."
                )
                elapsed = time.monotonic() - started
        self.assertLess(elapsed, 1.0)
        self.assertEqual(result.posted, 1)


@tag("tenants_rls")
class TokenExpiryIsolationTests(TestCase):
    def setUp(self):
        with rls_bypass():
            self.region = RegionConfig.get_default()
            self.school = School.objects.create(
                slug="social-expiry",
                subdomain="social-expiry",
                name="Social Expiry",
                default_region=self.region,
                timezone=self.region.timezone,
            )
            self.integration = SocialMediaIntegration.objects.create(
                school=self.school,
                provider=SocialProvider.X,
                handle="@expiry",
                encrypted_oauth_token="expired-token",
                token_expires_at=timezone.now() - timedelta(hours=1),
                feed_cache_json=[{"id": "stale", "text": "Cached"}],
            )

    def test_expired_token_marks_needs_reauth_and_serves_cache(self):
        result = sync_integration_feed(self.integration)
        self.integration.refresh_from_db()
        self.assertTrue(self.integration.needs_reauth)
        self.assertEqual(result["source"], "cache")
        self.assertEqual(result["items"][0]["id"], "stale")


@tag("tenants_rls")
class SocialIntegrationConstraintTests(TestCase):
    def setUp(self):
        with rls_bypass():
            self.region = RegionConfig.get_default()
            self.school = School.objects.create(
                slug="social-constraint",
                subdomain="social-constraint",
                name="Social Constraint",
                default_region=self.region,
                timezone=self.region.timezone,
            )

    def test_active_platform_provider_unique_without_school(self):
        with rls_bypass():
            SocialMediaIntegration.objects.create(
                school=None,
                provider=SocialProvider.LINKEDIN,
                handle="@platform",
                encrypted_oauth_token="platform-token-1",
            )
            with self.assertRaises(IntegrityError), transaction.atomic():
                SocialMediaIntegration.objects.create(
                    school=None,
                    provider=SocialProvider.LINKEDIN,
                    handle="@platform-duplicate",
                    encrypted_oauth_token="platform-token-2",
                )

    def test_active_tenant_provider_unique_per_school(self):
        with rls_bypass():
            SocialMediaIntegration.objects.create(
                school=self.school,
                provider=SocialProvider.INSTAGRAM,
                handle="@tenant",
                encrypted_oauth_token="tenant-token-1",
            )
            with self.assertRaises(IntegrityError), transaction.atomic():
                SocialMediaIntegration.objects.create(
                    school=self.school,
                    provider=SocialProvider.INSTAGRAM,
                    handle="@tenant-duplicate",
                    encrypted_oauth_token="tenant-token-2",
                )


@tag("tenants_rls")
class CrossTenantPostingTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        with rls_bypass():
            self.region = RegionConfig.get_default()
            self.alpha = School.objects.create(
                slug="social-post-alpha",
                subdomain="social-post-alpha",
                name="Alpha",
                default_region=self.region,
                timezone=self.region.timezone,
            )
            self.beta = School.objects.create(
                slug="social-post-beta",
                subdomain="social-post-beta",
                name="Beta",
                default_region=self.region,
                timezone=self.region.timezone,
            )
            self.admin = User.objects.create_user(
                username="social_post_admin",
                password="pass12345",
                role=User.Role.ADMIN,
            )
            SchoolMembership.objects.create(
                user=self.admin,
                school=self.alpha,
                role=User.Role.ADMIN,
                is_primary=True,
            )
            self.beta_integration = SocialMediaIntegration.objects.create(
                school=self.beta,
                provider=SocialProvider.FACEBOOK,
                handle="@beta",
                encrypted_oauth_token="beta-secret",
            )

    def test_publish_using_other_school_credentials_raises(self):
        request = self.factory.post("/", {"body": "Hack"}, format="json")
        request.school = self.alpha
        force_authenticate(request, user=self.admin)
        with self.assertRaises(SocialTenantScopeError):
            assert_integration_access(request, self.beta_integration, action="publish")
