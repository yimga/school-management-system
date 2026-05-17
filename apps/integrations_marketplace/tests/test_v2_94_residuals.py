"""Tests for v2.94 residuals (closes v2.89 honest-gap #5/#6/#8/#10).

  - #5  per-(integration_id, IP) rate-limit on webhook_receiver
  - #6  /integrations/test-webhook/<slug>/<id>/ synthetic delivery view
  - #8  /integrations/scopes/<slug>/ override form (narrow-only enforcement)
  - #10 manager-host cross-school rollup view (matrix data shape)

DB-free where possible: rate-limit uses Django's LocMem cache backend; the
test-webhook + scope-override + manager-rollup views are exercised via
RequestFactory + mocked ORM hits.
"""

from __future__ import annotations

import json
from unittest import mock

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase

from apps.integrations_marketplace import (
    manager_views as im_manager,
    views as im_views,
    webhooks as im_webhooks,
)


class _FakeSchool:
    def __init__(self, pk=1, name="Acme", is_active=True):
        self.pk = pk
        self.name = name
        self.is_active = is_active


class _FakeCampus:
    def __init__(self, pk=10, name="Main"):
        self.pk = pk
        self.name = name


class _FakeRow:
    def __init__(self, *, pk=1, slug="slack", secret="topsecret",
                 school=None, campus=None, config=None, is_active=True):
        self.pk = pk
        self.connector_slug = slug
        self.school = school
        self.campus = campus
        # Honor `config={}` explicitly; only fall back to the secret default
        # when caller passed nothing.
        if config is None:
            self.config = {"webhook_secret": secret}
        else:
            self.config = dict(config)
        self.is_active = is_active
        self.save_called = False

    def save(self, update_fields=None):
        self.save_called = True


# ---------------------------------------------------------------------------
# #5 — Rate limit
# ---------------------------------------------------------------------------

class RateLimitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def tearDown(self):
        cache.clear()

    def test_first_request_passes(self):
        req = self.factory.post("/integrations/webhook/x/1/")
        self.assertTrue(im_webhooks._rate_limit_ok(integration_id=1, request=req))

    def test_exceeds_threshold_blocks(self):
        # WEBHOOK_RATE_LIMIT_PER_MINUTE = 120
        for _ in range(im_webhooks.WEBHOOK_RATE_LIMIT_PER_MINUTE):
            req = self.factory.post("/integrations/webhook/x/1/", REMOTE_ADDR="1.2.3.4")
            self.assertTrue(im_webhooks._rate_limit_ok(integration_id=1, request=req))
        # 121st call from same IP + integration must fail.
        req = self.factory.post("/integrations/webhook/x/1/", REMOTE_ADDR="1.2.3.4")
        self.assertFalse(im_webhooks._rate_limit_ok(integration_id=1, request=req))

    def test_different_ip_has_independent_bucket(self):
        for _ in range(im_webhooks.WEBHOOK_RATE_LIMIT_PER_MINUTE):
            req = self.factory.post("/", REMOTE_ADDR="1.1.1.1")
            im_webhooks._rate_limit_ok(integration_id=1, request=req)
        # A different IP starts fresh.
        other = self.factory.post("/", REMOTE_ADDR="2.2.2.2")
        self.assertTrue(im_webhooks._rate_limit_ok(integration_id=1, request=other))

    def test_different_integration_has_independent_bucket(self):
        req_a = self.factory.post("/", REMOTE_ADDR="1.1.1.1")
        for _ in range(im_webhooks.WEBHOOK_RATE_LIMIT_PER_MINUTE):
            im_webhooks._rate_limit_ok(integration_id=1, request=req_a)
        # Another integration ID starts fresh on the same IP.
        self.assertTrue(im_webhooks._rate_limit_ok(integration_id=2, request=req_a))

    def test_falls_open_on_cache_exception(self):
        with mock.patch("django.core.cache.cache.incr",
                        side_effect=RuntimeError("redis down")), \
             mock.patch("django.core.cache.cache.set",
                        side_effect=RuntimeError("redis down")):
            req = self.factory.post("/", REMOTE_ADDR="1.1.1.1")
            # Falls open — never blocks production traffic.
            self.assertTrue(im_webhooks._rate_limit_ok(integration_id=99, request=req))

    def test_xff_header_is_respected(self):
        req = self.factory.post(
            "/", HTTP_X_FORWARDED_FOR="3.3.3.3, 4.4.4.4", REMOTE_ADDR="10.0.0.1"
        )
        self.assertEqual(im_webhooks._client_ip(req), "3.3.3.3")


# ---------------------------------------------------------------------------
# #6 — Test-webhook view
# ---------------------------------------------------------------------------

class TestWebhookViewTests(SimpleTestCase):
    def _request(self, school=None):
        req = RequestFactory().post(
            "/integrations/test-webhook/slack/1/"
        )
        req.school = school or _FakeSchool()
        req.user = mock.Mock(
            is_authenticated=True, is_staff=True, is_superuser=False, role="admin"
        )
        return req

    def test_no_school_returns_403(self):
        req = self._request(school=None)
        req.school = None
        with mock.patch.object(im_views, "render") as r:
            r.return_value = mock.Mock(status_code=403)
            resp = im_views.test_webhook(req, "slack", 1)
        self.assertEqual(resp.status_code, 403)

    def test_missing_row_returns_404(self):
        req = self._request()
        with mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter"
        ) as f:
            f.return_value.first.return_value = None
            resp = im_views.test_webhook(req, "slack", 1)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(json.loads(resp.content)["error"], "not_found")

    def test_missing_secret_returns_400(self):
        req = self._request()
        row = _FakeRow(slug="slack", config={})  # no webhook_secret
        with mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter"
        ) as f:
            f.return_value.first.return_value = row
            resp = im_views.test_webhook(req, "slack", 1)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            json.loads(resp.content)["error"], "no_webhook_secret_configured"
        )

    def test_slack_synthetic_delivery_verifies_and_dispatches(self):
        req = self._request()
        row = _FakeRow(slug="slack", secret="abc")
        # Patch _audit (would hit DB via compliance.AuditLog).
        with mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter"
        ) as f, mock.patch(
            "apps.integrations_marketplace.webhook_handlers._audit"
        ):
            f.return_value.first.return_value = row
            resp = im_views.test_webhook(req, "slack", 1)
        body = json.loads(resp.content)
        # If handler is registered, ok should be true; if not, verify still true.
        self.assertTrue(body["verify_ok"], body)
        # Slack handler is registered by AppConfig.ready().
        self.assertTrue(body["handler_present"])
        self.assertEqual(body["handler_status"], 200)


# ---------------------------------------------------------------------------
# #8 — Scope override view (narrow-only enforcement)
# ---------------------------------------------------------------------------

class ScopeOverrideViewTests(SimpleTestCase):
    def _request(self, *, method="GET", post_data=None):
        factory = RequestFactory()
        if method == "POST":
            req = factory.post("/integrations/scopes/zoom/", post_data or {})
        else:
            req = factory.get("/integrations/scopes/zoom/")
        req.school = _FakeSchool()
        req.user = mock.Mock(
            is_authenticated=True, is_staff=True, is_superuser=False, role="admin"
        )
        # Required by django messages framework when we redirect.
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req, "session", "session")
        setattr(req, "_messages", FallbackStorage(req))
        return req

    def test_post_widening_scope_is_rejected(self):
        # Zoom defaults are: meeting:write, meeting:read, user:read.
        req = self._request(method="POST", post_data={"scopes": [
            "meeting:read", "admin:write",  # 2nd is OUTSIDE the default set
        ]})
        row = _FakeRow(slug="zoom", config={})
        with mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter"
        ) as f:
            qs = mock.Mock()
            qs.filter.return_value = qs
            qs.first.return_value = row
            f.return_value = qs
            resp = im_views.scope_override(req, "zoom")
        self.assertEqual(resp.status_code, 302)  # redirected back to form with error
        self.assertFalse(row.save_called)  # MUST NOT have persisted the widening
        self.assertNotIn("scopes_override", row.config)

    def test_post_subset_is_saved(self):
        req = self._request(method="POST", post_data={
            "scopes": ["meeting:read", "user:read"],  # subset of defaults
        })
        row = _FakeRow(slug="zoom", config={})
        with mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter"
        ) as f:
            qs = mock.Mock()
            qs.filter.return_value = qs
            qs.first.return_value = row
            f.return_value = qs
            resp = im_views.scope_override(req, "zoom")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(row.save_called)
        self.assertEqual(row.config["scopes_override"], ["meeting:read", "user:read"])

    def test_post_with_full_default_set_clears_override(self):
        req = self._request(method="POST", post_data={
            "scopes": ["meeting:write", "meeting:read", "user:read"],
        })
        row = _FakeRow(slug="zoom", config={"scopes_override": ["meeting:read"]})
        with mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter"
        ) as f:
            qs = mock.Mock()
            qs.filter.return_value = qs
            qs.first.return_value = row
            f.return_value = qs
            im_views.scope_override(req, "zoom")
        # Full set selected → override is cleared (back to defaults).
        self.assertNotIn("scopes_override", row.config)

    def test_get_renders_with_selected_set(self):
        req = self._request(method="GET")
        row = _FakeRow(slug="zoom", config={"scopes_override": ["meeting:read"]})
        captured = {}

        def fake_render(req, tmpl, ctx, **kw):
            captured["ctx"] = ctx
            from django.http import HttpResponse
            return HttpResponse("ok")

        with mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter"
        ) as f, mock.patch.object(im_views, "render", side_effect=fake_render):
            qs = mock.Mock()
            qs.filter.return_value = qs
            qs.first.return_value = row
            f.return_value = qs
            im_views.scope_override(req, "zoom")
        self.assertEqual(captured["ctx"]["selected"], {"meeting:read"})
        self.assertTrue(captured["ctx"]["is_overriding"])

    def test_non_oauth_connector_redirects(self):
        req = self._request(method="GET")
        # `mailgun` is api_key, not OAuth — must refuse.
        resp = im_views.scope_override(req, "mailgun")
        self.assertEqual(resp.status_code, 302)


# ---------------------------------------------------------------------------
# #10 — Cross-school manager rollup
# ---------------------------------------------------------------------------

class ManagerRollupTests(SimpleTestCase):
    def test_rollup_groups_rows_by_school_and_connector(self):
        # Build 2 schools, 3 rows total — one school has Zoom + Slack, one only Slack.
        s_a = _FakeSchool(pk=1, name="Alpha")
        s_b = _FakeSchool(pk=2, name="Beta")
        row1 = _FakeRow(pk=1, slug="zoom", school=s_a)
        row2 = _FakeRow(pk=2, slug="slack", school=s_a)
        row3 = _FakeRow(pk=3, slug="slack", school=s_b)

        # The view iterates two querysets: rows + schools. Mock both.
        rows_qs = mock.Mock()
        rows_qs.iterator.return_value = iter([row1, row2, row3])
        rows_qs.select_related.return_value = rows_qs
        rows_qs.order_by.return_value = rows_qs
        rows_qs.filter.return_value = rows_qs
        rows_qs.exclude.return_value = rows_qs
        rows_qs.count.return_value = 3

        schools_qs = mock.Mock()
        schools_qs.order_by.return_value = iter([s_a, s_b])
        schools_qs.filter.return_value = schools_qs

        req = RequestFactory().get("/manager/integrations-rollup/")
        req.user = mock.Mock(
            is_authenticated=True, is_staff=True, is_superuser=True, role="superadmin"
        )

        captured: dict = {}

        def fake_render(req, tmpl, ctx, **kw):
            captured["ctx"] = ctx
            from django.http import HttpResponse
            return HttpResponse("ok")

        with mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter",
            return_value=rows_qs,
        ), mock.patch(
            "apps.schools.models.School.objects.filter",
            return_value=schools_qs,
        ), mock.patch.object(im_manager, "render", side_effect=fake_render):
            im_manager.manager_integrations_rollup(req)

        ctx = captured["ctx"]
        self.assertEqual(ctx["total_schools"], 2)
        self.assertEqual(ctx["total_rows"], 3)
        # Alpha has 2 connectors, Beta has 1.
        alpha_entry = next(e for e in ctx["schools"] if e["school"].name == "Alpha")
        beta_entry = next(e for e in ctx["schools"] if e["school"].name == "Beta")
        self.assertEqual(set(alpha_entry["by_connector"].keys()), {"zoom", "slack"})
        self.assertEqual(set(beta_entry["by_connector"].keys()), {"slack"})
        # Schools-connected count per connector.
        slack_meta = next(c for c in ctx["connectors"] if c["slug"] == "slack")
        zoom_meta = next(c for c in ctx["connectors"] if c["slug"] == "zoom")
        self.assertEqual(slack_meta["schools_connected"], 2)
        self.assertEqual(zoom_meta["schools_connected"], 1)
