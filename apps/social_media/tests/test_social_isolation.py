"""
Adversarial multi-tenant isolation tests for the social media engine.

Covers feed boundary breach, platform vs tenant scope, and 429 cache fallback.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

from django.db import models
from django.test import RequestFactory, SimpleTestCase, TestCase, tag
from rest_framework.test import force_authenticate

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.schools.rls_context import rls_bypass
from apps.siteconfig.models import RegionConfig
from apps.social_media.api_views import SocialFeedAPI
from apps.social_media.models import SocialMediaIntegration, SocialProvider
from apps.social_media.scope import SocialTenantScopeError, assert_integration_access
from apps.social_media.services import aggregator, providers, throttle
from apps.social_media.services.aggregator import sync_integration_feed


class SocialScopeUnitTests(SimpleTestCase):
    def test_throttle_isolated_per_scope(self):
        throttle.reset_scope("tenant:alpha")
        throttle.reset_scope("tenant:beta")
        self.assertTrue(throttle.try_consume("tenant:alpha", "x", cost=30.0))
        self.assertFalse(throttle.try_consume("tenant:alpha", "x", cost=1.0))
        self.assertTrue(throttle.try_consume("tenant:beta", "x", cost=1.0))

    def test_rate_limit_falls_back_to_cache(self):
        integration = Mock()
        integration.id = "00000000-0000-0000-0000-000000000001"
        integration.school_id = None
        integration.provider = "x"
        integration.encrypted_oauth_token = "enc-token"
        integration.token_expired.return_value = False
        integration.feed_cache_json = [{"id": "cached-1", "text": "Hello"}]
        integration.feed_cached_at = None
        integration.needs_reauth = False
        integration.save = Mock()

        with patch(
            "apps.social_media.services.aggregator.providers.fetch_feed_items",
            side_effect=providers.ProviderRateLimitError(),
        ):
            result = sync_integration_feed(integration)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "cache")
        self.assertEqual(result["items"][0]["id"], "cached-1")


class SocialModelConstraintUnitTests(SimpleTestCase):
    def test_active_provider_constraints_split_platform_and_tenant_scope(self):
        constraints = {
            constraint.name: constraint
            for constraint in SocialMediaIntegration._meta.constraints
        }
        self.assertIn("uniq_active_social_provider_per_school", constraints)
        self.assertIn("uniq_active_platform_social_provider", constraints)

        per_school = constraints["uniq_active_social_provider_per_school"]
        self.assertEqual(list(per_school.fields), ["school", "provider"])
        self.assertEqual(
            per_school.condition,
            models.Q(is_active=True, school__isnull=False),
        )

        platform = constraints["uniq_active_platform_social_provider"]
        self.assertEqual(list(platform.fields), ["provider"])
        self.assertEqual(
            platform.condition,
            models.Q(is_active=True, school__isnull=True),
        )


@tag("tenants_rls")
class SocialFeedBoundaryTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        with rls_bypass():
            self.region = RegionConfig.get_default()
            self.alpha = School.objects.create(
                slug="social-alpha",
                subdomain="social-alpha",
                name="Social Alpha",
                default_region=self.region,
                timezone=self.region.timezone,
            )
            self.beta = School.objects.create(
                slug="social-beta",
                subdomain="social-beta",
                name="Social Beta",
                default_region=self.region,
                timezone=self.region.timezone,
            )
            self.admin_alpha = User.objects.create_user(
                username="social_admin_alpha",
                password="pass12345",
                role=User.Role.ADMIN,
            )
            SchoolMembership.objects.create(
                user=self.admin_alpha,
                school=self.alpha,
                role=User.Role.ADMIN,
                is_primary=True,
            )
            SocialMediaIntegration.objects.create(
                school=self.beta,
                provider=SocialProvider.FACEBOOK,
                handle="@beta",
                encrypted_oauth_token="secret-beta",
                feed_cache_json=[{"id": "beta-post", "text": "Beta only"}],
            )
            SocialMediaIntegration.objects.create(
                school=self.alpha,
                provider=SocialProvider.X,
                handle="@alpha",
                encrypted_oauth_token="secret-alpha",
                feed_cache_json=[{"id": "alpha-post", "text": "Alpha"}],
            )

    def test_feed_api_never_returns_other_tenant_items(self):
        view = SocialFeedAPI.as_view()
        request = self.factory.get("/api/v1/social/feed/")
        request.school = self.alpha
        force_authenticate(request, user=self.admin_alpha)
        with rls_bypass():
            response = view(request)
        self.assertEqual(response.status_code, 200)
        ids = {item.get("id") for item in response.data["items"]}
        self.assertIn("alpha-post", ids)
        self.assertNotIn("beta-post", ids)

    def test_cross_tenant_publish_blocked(self):
        beta_integration = SocialMediaIntegration.objects.get(school=self.beta)
        request = self.factory.post("/api/v1/social/publish/", {"body": "Hijack"}, format="json")
        request.school = self.alpha
        force_authenticate(request, user=self.admin_alpha)
        with self.assertRaises(SocialTenantScopeError):
            assert_integration_access(request, beta_integration, action="publish")


@tag("tenants_rls")
class PlatformManagerScopeTests(TestCase):
    def setUp(self):
        with rls_bypass():
            self.region = RegionConfig.get_default()
            self.school = School.objects.create(
                slug="social-tenant",
                subdomain="social-tenant",
                name="Social Tenant",
                default_region=self.region,
                timezone=self.region.timezone,
            )
            SocialMediaIntegration.objects.create(
                school=None,
                provider=SocialProvider.LINKEDIN,
                handle="@runmycampus",
                encrypted_oauth_token="platform-token",
                feed_cache_json=[{"id": "corp-1", "text": "Platform"}],
            )
            SocialMediaIntegration.objects.create(
                school=self.school,
                provider=SocialProvider.INSTAGRAM,
                handle="@school",
                encrypted_oauth_token="tenant-token",
                feed_cache_json=[{"id": "school-1", "text": "School"}],
            )

    def test_platform_feed_does_not_include_tenant_rows(self):
        items = aggregator.read_cached_feed(platform_scope=True)
        ids = {i.get("id") for i in items}
        self.assertIn("corp-1", ids)
        self.assertNotIn("school-1", ids)

    def test_tenant_feed_does_not_include_platform_rows(self):
        items = aggregator.read_cached_feed(school_id=self.school.id)
        ids = {i.get("id") for i in items}
        self.assertIn("school-1", ids)
        self.assertNotIn("corp-1", ids)
