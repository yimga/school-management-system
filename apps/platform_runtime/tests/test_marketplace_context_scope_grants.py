"""Regression: the tenant marketplace context must load granted scopes.

``_step10_marketplace`` iterated ``inst.scope_grants`` (a reverse-FK
RelatedManager) directly, which raised ``TypeError: 'RelatedManager' object is
not iterable``. The surrounding broad ``except`` swallowed it, aborting the
WHOLE marketplace load on the first installation — so granted scopes, workflow
actions/conditions, and integration adapters were silently dropped on every
request (and the log filled with "Marketplace context load failed" warnings).
"""

from django.test import TestCase

from apps.marketplace.models import (
    AppInstallation,
    AppScope,
    MarketplaceApp,
    ScopeGrant,
)
from apps.platform_runtime.runtime_resolver import _step10_marketplace
from apps.schools.models import School


class MarketplaceContextScopeGrantsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Marketplace School",
            slug="marketplace-school",
            subdomain="marketplace-school",
            country_code="CM",
            is_active=True,
        )
        self.app = MarketplaceApp.objects.create(
            slug="mp-scope-app",
            name="Marketplace Scope App",
            version="1.0.0",
            manifest={"integration_adapters": [{"id": "grade-sync"}]},
            is_intentionally_free=True,
        )
        self.installation = AppInstallation.objects.create(
            school=self.school, app=self.app
        )
        self.scope = AppScope.objects.create(
            app=self.app, scope_code="students:read"
        )
        ScopeGrant.objects.create(installation=self.installation, scope=self.scope)

    def test_granted_scope_is_loaded_not_swallowed(self):
        ctx = _step10_marketplace(self.school)
        # Before the fix this was empty: the RelatedManager TypeError aborted the
        # loop before any scope (or the integration adapter after it) was read.
        self.assertIn("students:read", ctx.granted_scopes)
        self.assertEqual(len(ctx.installed_apps), 1)
        self.assertIn({"id": "grade-sync"}, ctx.integration_adapters)

    def test_pending_scope_is_not_granted(self):
        """A non-granted scope must be skipped without aborting the load."""
        other_scope = AppScope.objects.create(
            app=self.app, scope_code="grades:write"
        )
        ScopeGrant.objects.create(
            installation=self.installation,
            scope=other_scope,
            status=ScopeGrant.GrantStatus.PENDING,
        )
        ctx = _step10_marketplace(self.school)
        self.assertIn("students:read", ctx.granted_scopes)
        self.assertNotIn("grades:write", ctx.granted_scopes)
