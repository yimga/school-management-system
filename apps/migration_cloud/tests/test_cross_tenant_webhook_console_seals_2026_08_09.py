"""Regression seals for two cross-tenant leaks found in the 2026-08-09 re-audit.

Each test FAILS against the pre-fix code and PASSES against the fix.

  1. ``WebhookSubscriptionViewSet`` keyed cross-tenant "see all" and the
     ``?tenant_id=`` override on bare ``user.is_staff``. Tenant admins are
     auto-provisioned ``is_staff=True`` (``ensure_default_tenant_admin``), so on
     their own subdomain they LISTED every tenant's subscriptions (a live read
     leak: endpoint URLs, event types, secret preview). The CREATE-side
     ``?tenant_id`` override was a latent hijack — only blocked today because
     ``School`` uses a UUID pk and the old ``int(explicit)`` always failed; the
     moment School pks were integers (or the int() bug "fixed") a tenant admin
     could bind a webhook to ANOTHER tenant and exfiltrate its signed lifecycle
     payloads. Both are now gated on ``_is_operator_shell_request`` (control-plane
     access on the manager/local host), mirroring the sealed ``BundleViewSet``,
     and the operator override is resolved by real School pk (UUID-safe).

  2. ``MigrationCloudConsoleView`` (portal shell) left its bundle queryset
     UNFILTERED when the tenant host did not resolve a school, listing every
     tenant's bundles. It now fails closed (empty) on a null tenant.
"""

from __future__ import annotations

from unittest import mock

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.migration_cloud.api.webhooks import WebhookSubscriptionViewSet
from apps.migration_cloud.models import (
    BundleStatus,
    IntakeMethod,
    MigrationBundle,
    MigrationCloudWebhookSubscription,
)
from apps.migration_cloud.views import MigrationCloudConsoleView
from apps.schools.models import School, SchoolMembership


def _school(slug: str) -> School:
    return School.objects.create(name=slug, slug=slug, subdomain=slug, is_active=True)


def _sub(school: School, url: str) -> MigrationCloudWebhookSubscription:
    return MigrationCloudWebhookSubscription.objects.create(
        tenant_id=school.pk,
        url=url,
        event_types=[],
        secret_hash="a" * 64,
        secret_ciphertext=b"whsec_x",
        active=True,
    )


def _request(school=None, *, user=None, host_kind=None, tenant_id=None):
    rf = RequestFactory()
    path = "/portal/configure/migration/api/v1/webhooks/"
    if tenant_id is not None:
        path += f"?tenant_id={tenant_id}"
    request = rf.get(path)
    if user is not None:
        request.user = user
    if school is not None:
        request.school = school
    if host_kind is not None:
        request.public_host_kind = host_kind
    # DRF exposes query_params on the wrapped Request; the raw factory request
    # does not, so mirror GET onto it for the resolver under test.
    request.query_params = request.GET
    return request


class WebhookCrossTenantSealTests(TestCase):
    """Seal #1 — webhook list/create are operator-gated, not is_staff-gated."""

    def setUp(self):
        self.school_a = _school("wh-seal-a")
        self.school_b = _school("wh-seal-b")
        # Tenant admin of A: is_staff=True but has a SchoolMembership, so
        # user_has_control_plane_access() is False → NOT an operator.
        self.tenant_admin = User.objects.create_user(
            username="wh_tenant_admin", password="x", is_staff=True,
        )
        SchoolMembership.objects.create(user=self.tenant_admin, school=self.school_a)
        # Genuine operator: superuser → control-plane access.
        self.operator = User.objects.create_superuser(
            username="wh_operator", password="x", email="op@example.com",
        )
        self.a_sub = _sub(self.school_a, "https://hooks.a.example/x")
        self.b_sub = _sub(self.school_b, "https://hooks.b.example/x")

    def _queryset_tenant_ids(self, request):
        view = WebhookSubscriptionViewSet()
        view.request = request
        return set(view.get_queryset().values_list("tenant_id", flat=True))

    def test_tenant_admin_list_confined_to_own_school(self):
        # is_staff=True but NOT an operator: must see ONLY school A's rows.
        ids = self._queryset_tenant_ids(
            _request(school=self.school_a, user=self.tenant_admin)
        )
        self.assertEqual(ids, {self.school_a.pk})
        self.assertNotIn(self.school_b.pk, ids)

    def test_operator_list_sees_all_tenants(self):
        # Operator on the manager host retains cross-tenant visibility.
        ids = self._queryset_tenant_ids(
            _request(school=None, user=self.operator, host_kind="manager")
        )
        self.assertEqual(ids, {self.school_a.pk, self.school_b.pk})

    def test_tenant_admin_cannot_target_foreign_tenant_on_create(self):
        # A tenant admin of A passing ?tenant_id=B must still bind to A.
        request = _request(
            school=self.school_a, user=self.tenant_admin, tenant_id=self.school_b.pk,
        )
        view = WebhookSubscriptionViewSet()
        resolved = view._resolve_target_tenant_id(request)
        self.assertEqual(resolved, self.school_a.pk)

    def test_operator_may_target_explicit_tenant_on_create(self):
        request = _request(
            school=None, user=self.operator, host_kind="manager",
            tenant_id=self.school_b.pk,
        )
        view = WebhookSubscriptionViewSet()
        resolved = view._resolve_target_tenant_id(request)
        self.assertEqual(resolved, self.school_b.pk)

    def test_tenant_admin_list_sets_operator_shell_false(self):
        # Guardrail: confirm the tenant admin is not treated as an operator.
        from apps.migration_cloud.api.permissions import _is_operator_shell_request

        request = _request(
            school=self.school_a, user=self.tenant_admin, host_kind="manager",
        )
        self.assertFalse(_is_operator_shell_request(request))


class ConsoleFailClosedTests(TestCase):
    """Seal #2 — portal console fails closed when no tenant is resolved."""

    def setUp(self):
        self.rf = RequestFactory()
        self.school_a = _school("console-seal-a")
        self.school_b = _school("console-seal-b")
        self.user = User.objects.create_user(username="console_seal_user", password="x")
        self.a = MigrationBundle.objects.create(
            label="console-a", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="console-a", status=BundleStatus.MAPPED, school=self.school_a,
        )
        self.b = MigrationBundle.objects.create(
            label="console-b", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="console-b", status=BundleStatus.MAPPED, school=self.school_b,
        )

    def _console_bundles(self, school):
        """Invoke the console GET and capture the bundle list it would render."""
        request = self.rf.get("/portal/configure/migration/")
        request.user = self.user
        if school is not None:
            request.school = school
        captured = {}

        def _fake_render(req, template, context, *a, **k):
            captured["bundles"] = list(context.get("bundles", []))
            from django.http import HttpResponse

            return HttpResponse(b"ok")

        with mock.patch("apps.migration_cloud.views.render", _fake_render), \
                mock.patch(
                    "apps.migration_cloud.views._enforce_portal_entitlement",
                    return_value=None,
                ):
            MigrationCloudConsoleView.as_view()(request, shell="portal")
        return captured.get("bundles", [])

    def test_portal_null_tenant_lists_nothing(self):
        bundles = self._console_bundles(school=None)
        self.assertEqual(bundles, [])

    def test_portal_resolved_tenant_lists_only_own(self):
        bundles = self._console_bundles(school=self.school_a)
        labels = {b.label for b in bundles}
        self.assertIn("console-a", labels)
        self.assertNotIn("console-b", labels)
