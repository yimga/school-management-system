"""Developer platform: lifecycle, scopes, sandbox, webhooks, dependency resolution."""

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.apicenter.models import APIKey, _hash_secret
from apps.marketplace.lifecycle import (
    emit_webhook_audit,
    install_app,
    missing_dependencies,
    rollback_app,
    upgrade_app,
)
from apps.marketplace.models import (
    AppAuditLog,
    AppScope,
    MarketplaceApp,
    PublisherOrganization,
)
from apps.marketplace.permissions_runtime import effective_scopes_for_api_key
from apps.marketplace.sandbox import safe_queryset_for_app
from apps.marketplace.semver_utils import compare_semver
from apps.schools.models import School


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class DeveloperPlatformTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Dev Plat School",
            slug="dev-plat-school",
            subdomain="dev-plat-school",
            is_active=True,
        )
        pub, _ = PublisherOrganization.objects.get_or_create(
            slug="pub-devplat",
            defaults={
                "name": "Pub",
                "verification_status": PublisherOrganization.VerificationStatus.VERIFIED,
            },
        )
        self.base_app = MarketplaceApp.objects.create(
            publisher=pub,
            slug="base-dep-app",
            name="Base",
            version="1.0.0",
            kind=MarketplaceApp.AppKind.FIRST_PARTY,
            is_intentionally_free=True,
        )
        self.child_app = MarketplaceApp.objects.create(
            publisher=pub,
            slug="child-app",
            name="Child",
            version="1.0.0",
            kind=MarketplaceApp.AppKind.FIRST_PARTY,
            required_apps=[self.base_app.app_key],
            is_intentionally_free=True,
        )
        self.app = MarketplaceApp.objects.create(
            publisher=pub,
            slug="scoped-app",
            name="Scoped",
            version="1.0.0",
            kind=MarketplaceApp.AppKind.FIRST_PARTY,
            install_hooks=["https://hooks.example/install"],
            is_intentionally_free=True,
        )
        AppScope.objects.create(app=self.app, scope_code="ping:read", description="")

    def _host(self):
        return {"HTTP_HOST": f"{self.school.subdomain}.runmycampus.com"}

    def test_compare_semver(self):
        self.assertEqual(compare_semver("1.0.0", "1.0.0"), 0)
        self.assertLess(compare_semver("1.0.0", "1.1.0"), 0)

    def test_missing_dependencies(self):
        miss = missing_dependencies(self.school.id, self.child_app)
        self.assertEqual(miss, [self.base_app.app_key])
        install_app(school=self.school, app=self.base_app, actor=None)
        miss2 = missing_dependencies(self.school.id, self.child_app)
        self.assertEqual(miss2, [])

    def test_install_upgrade_rollback_semver(self):
        inst = install_app(school=self.school, app=self.app, grant_scope_codes=["ping:read"])
        self.assertEqual(inst.installed_version, "1.0.0")
        self.app.version = "1.1.0"
        self.app.save(update_fields=["version"])
        upgrade_app(installation=inst, target=self.app, actor=None)
        inst.refresh_from_db()
        self.assertEqual(inst.installed_version, "1.1.0")
        rollback_app(installation=inst, previous_version="1.0.0", actor=None)
        inst.refresh_from_db()
        self.assertEqual(inst.installed_version, "1.0.0")

    def test_effective_scopes_for_api_key_merges_grants(self):
        inst = install_app(school=self.school, app=self.app, grant_scope_codes=["ping:read"])
        key_prefix, raw = APIKey.generate_key_pair()
        key = APIKey.objects.create(
            school=self.school,
            name="k",
            key_prefix=key_prefix,
            secret_hash=_hash_secret(raw),
            scopes=["catalog:read"],
            marketplace_installation=inst,
        )
        eff = effective_scopes_for_api_key(key)
        self.assertIn("ping:read", eff)
        self.assertIn("catalog:read", eff)

    def test_webhook_audit_record(self):
        inst = install_app(school=self.school, app=self.app)
        emit_webhook_audit(inst, "test.event", {"x": 1})
        log = AppAuditLog.objects.filter(action="marketplace.webhook.test.event").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.payload.get("x"), 1)

    def test_api_middleware_and_scoped_endpoint(self):
        inst = install_app(school=self.school, app=self.app, grant_scope_codes=["ping:read"])
        key_prefix, raw = APIKey.generate_key_pair()
        APIKey.objects.create(
            school=self.school,
            name="k2",
            key_prefix=key_prefix,
            secret_hash=_hash_secret(raw),
            scopes=[],
            marketplace_installation=inst,
        )
        client = Client()
        ctx_url = reverse("api_v1:platform-integration-context")
        r1 = client.get(ctx_url, HTTP_AUTHORIZATION=f"Bearer {raw}", **self._host())
        self.assertEqual(r1.status_code, 200)
        data = r1.json()
        self.assertTrue(data.get("app_auth"))
        self.assertIn("ping:read", data.get("app_scope") or [])

        ping_url = reverse("api_v1:platform-scoped-ping")
        r2 = client.get(ping_url, HTTP_AUTHORIZATION=f"Bearer {raw}", **self._host())
        self.assertEqual(r2.status_code, 200, msg=r2.content)

        r3 = client.get(ping_url, **self._host())
        self.assertEqual(r3.status_code, 401)

    def test_safe_queryset_for_app_tenant_isolation(self):
        from apps.marketplace.models import AppInstallation as AI

        other = School.objects.create(
            name="Other",
            slug="other-s",
            subdomain="other-s",
            is_active=True,
        )
        inst_other = install_app(school=other, app=self.app)

        class Req:
            school = self.school
            app_api_key = object()
            app_installation = inst_other

        req = Req()
        qs = safe_queryset_for_app(AI.objects.all(), req)
        self.assertEqual(qs.count(), 0)
