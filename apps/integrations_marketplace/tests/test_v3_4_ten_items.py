"""Tests for v3.4 — closes 10 honest gaps from the v3.1 close-out:

  #1  subscribe_for_row (Google + Graph + auto-fire from connector_connected)
  #2  Slack/Teams/Discord send helpers (via apps.communication.integrations)
  #3  connector_connected / connector_disconnected lifecycle signals
  #4  rotate_webhook_secret view (one-click)
  #5  bulk_disconnect view (requires confirm=YES)
  #6  integrations_data_inventory_csv export shape
  #7  per-tenant WEBHOOK_RATE_LIMIT_PER_MINUTE override via school.settings
  #8  rate_limit_check unified helper
  #9  deprecated Connector field + connect refusal for new tenants
  #10 manager_bulk_prestage (idempotent + connector validation)
"""

from __future__ import annotations

import json
import time
from unittest import mock

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase

from apps.integrations_marketplace import (
    manager_views as im_manager,
    subscription_subscribe as im_subscribe,
    views as im_views,
    webhooks as im_webhooks,
)
from apps.integrations_marketplace.signals import (
    connector_connected,
    connector_disconnected,
)


class _FakeSchool:
    def __init__(self, pk=1, name="Acme", settings=None, is_active=True):
        self.pk = pk
        self.name = name
        self.settings = settings or {}
        self.is_active = is_active


class _FakeCampus:
    def __init__(self, pk=10, name="Main"):
        self.pk = pk
        self.name = name


class _FakeRow:
    def __init__(self, *, pk=1, slug="google_calendar", config=None,
                 school=None, campus=None, is_active=True):
        self.pk = pk
        self.connector_slug = slug
        self.config = dict(config or {})
        self.school = school
        self.campus = campus
        self.is_active = is_active
        self.saved_with: list[list[str]] = []

    def save(self, update_fields=None):
        self.saved_with.append(list(update_fields or []))


# ---------------------------------------------------------------------------
# #1 subscribe_for_row
# ---------------------------------------------------------------------------

class SubscribeForRowTests(SimpleTestCase):
    def test_no_subscriber_for_slug(self):
        row = _FakeRow(slug="slack")  # slack has no push subscription
        out = im_subscribe.subscribe_for_row(row)
        self.assertEqual(out["status"], "no_subscribe_for_slug")

    def test_idempotent_when_already_subscribed(self):
        row = _FakeRow(slug="google_calendar", config={
            "access_token": "tok",
            "push_subscription": {"provider": "google_calendar", "channel_id": "x"},
        })
        out = im_subscribe.subscribe_for_row(row)
        self.assertEqual(out["status"], "already_subscribed")

    def test_no_webhook_url_when_OAUTH_CALLBACK_BASE_URL_unset(self):
        row = _FakeRow(slug="google_calendar", config={"access_token": "tok"})
        with mock.patch.object(im_subscribe.settings, "OAUTH_CALLBACK_BASE_URL",
                               "", create=True):
            out = im_subscribe.subscribe_for_row(row)
        self.assertEqual(out["status"], "no_webhook_url")

    def test_google_subscribe_success_persists_subscription(self):
        row = _FakeRow(slug="google_calendar", config={"access_token": "tok"})
        with mock.patch.object(im_subscribe.settings, "OAUTH_CALLBACK_BASE_URL",
                               "https://app.example.com", create=True), \
             mock.patch.object(im_subscribe, "_post_json",
                               return_value=(200, {"id": "ch1", "resourceId": "r1"})):
            out = im_subscribe.subscribe_for_row(row)
        self.assertEqual(out["status"], "subscribed")
        self.assertEqual(row.config["push_subscription"]["channel_id"], "ch1")
        self.assertEqual(row.config["push_subscription"]["provider"], "google_calendar")

    def test_graph_subscribe_success_persists_subscription_id(self):
        row = _FakeRow(slug="outlook_mail", config={"access_token": "tok"})
        with mock.patch.object(im_subscribe.settings, "OAUTH_CALLBACK_BASE_URL",
                               "https://app.example.com", create=True), \
             mock.patch.object(im_subscribe, "_post_json",
                               return_value=(201, {"id": "sub-xyz"})):
            out = im_subscribe.subscribe_for_row(row)
        self.assertEqual(out["status"], "subscribed")
        self.assertEqual(row.config["push_subscription"]["subscription_id"], "sub-xyz")
        self.assertIn("client_state", row.config["push_subscription"])

    def test_subscribe_unauthorized_does_not_persist(self):
        row = _FakeRow(slug="google_calendar", config={"access_token": "tok"})
        with mock.patch.object(im_subscribe.settings, "OAUTH_CALLBACK_BASE_URL",
                               "https://app.example.com", create=True), \
             mock.patch.object(im_subscribe, "_post_json", return_value=(401, {})):
            out = im_subscribe.subscribe_for_row(row)
        self.assertEqual(out["status"], "unauthorized")
        self.assertNotIn("push_subscription", row.config)


# ---------------------------------------------------------------------------
# #2 Chat send helpers
# ---------------------------------------------------------------------------

class ChatSendHelpersTests(SimpleTestCase):
    def test_slack_send_requires_token_and_channel(self):
        from apps.communication.integrations import SlackIntegration
        with mock.patch(
            "apps.communication.integrations._resolve_connector_config_safe",
            return_value={},
        ):
            s = SlackIntegration(school=None)
        self.assertFalse(s.send_message("#x", "hi"))

    def test_slack_send_posts_to_chat_postMessage(self):
        from apps.communication.integrations import SlackIntegration
        with mock.patch(
            "apps.communication.integrations._resolve_connector_config_safe",
            return_value={"access_token": "xoxb-1", "default_channel": "#general"},
        ):
            s = SlackIntegration(school=None)
        fake_resp = mock.Mock(status_code=200)
        fake_resp.json.return_value = {"ok": True}
        with mock.patch("requests.post", return_value=fake_resp) as p:
            ok = s.send_message(None, "hello")
        self.assertTrue(ok)
        url, kwargs = p.call_args.args, p.call_args.kwargs
        self.assertEqual(url[0], "https://slack.com/api/chat.postMessage")
        self.assertEqual(kwargs["json"]["channel"], "#general")

    def test_teams_send_posts_to_graph(self):
        from apps.communication.integrations import TeamsIntegration
        with mock.patch(
            "apps.communication.integrations._resolve_connector_config_safe",
            return_value={"access_token": "tok", "default_chat_id": "19:abc"},
        ):
            t = TeamsIntegration(school=None)
        fake_resp = mock.Mock(status_code=201)
        with mock.patch("requests.post", return_value=fake_resp) as p:
            ok = t.send_message(None, "hi")
        self.assertTrue(ok)
        self.assertIn("/chats/19:abc/messages", p.call_args.args[0])

    def test_discord_send_uses_webhook_url(self):
        from apps.communication.integrations import DiscordIntegration
        with mock.patch(
            "apps.communication.integrations._resolve_connector_config_safe",
            return_value={"webhook_url": "https://discord.com/api/webhooks/1/abc"},
        ):
            d = DiscordIntegration(school=None)
        fake_resp = mock.Mock(status_code=204)
        with mock.patch("requests.post", return_value=fake_resp) as p:
            ok = d.send_message(None, "hi", username="rmc-bot")
        self.assertTrue(ok)
        self.assertEqual(p.call_args.kwargs["json"]["username"], "rmc-bot")


# ---------------------------------------------------------------------------
# #3 Lifecycle signals
# ---------------------------------------------------------------------------

class LifecycleSignalsTests(SimpleTestCase):
    def setUp(self):
        self.events: list[dict] = []

        def rx(sender, **kw):
            self.events.append({k: v for k, v in kw.items() if k != "signal"})

        self._rx = rx
        connector_connected.connect(rx, dispatch_uid="im_t34_conn", weak=False)
        connector_disconnected.connect(rx, dispatch_uid="im_t34_disc", weak=False)
        self.addCleanup(lambda: (
            connector_connected.disconnect(dispatch_uid="im_t34_conn"),
            connector_disconnected.disconnect(dispatch_uid="im_t34_disc"),
        ))

    def test_persist_oauth_tokens_fires_connector_connected(self):
        from apps.integrations_marketplace import oauth as im_oauth
        from apps.integrations_marketplace.connector_registry import get_connector

        connector = get_connector("zoom")
        school = _FakeSchool()
        fake_row = mock.Mock()
        with mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects."
            "update_or_create",
            return_value=(fake_row, True),
        ):
            im_oauth.persist_oauth_tokens(
                connector=connector, school=school, campus=None,
                token_response={"access_token": "x", "scope": "meeting:read"},
            )
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["connector"], "zoom")
        self.assertEqual(self.events[0]["action"], "connected")
        self.assertIs(self.events[0]["row"], fake_row)


# ---------------------------------------------------------------------------
# #4 rotate_webhook_secret view
# ---------------------------------------------------------------------------

class RotateWebhookSecretTests(SimpleTestCase):
    def _request(self, school):
        req = RequestFactory().post("/integrations/rotate-secret/slack/1/")
        req.school = school
        req.user = mock.Mock(is_authenticated=True, is_staff=True,
                             is_superuser=False, role="admin")
        return req

    def test_rotate_writes_new_secret_and_preserves_prev(self):
        school = _FakeSchool()
        row = _FakeRow(slug="slack", config={"webhook_secret": "old"},
                        school=school)
        with mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects."
            "filter"
        ) as f:
            f.return_value.first.return_value = row
            resp = im_views.rotate_webhook_secret(self._request(school), "slack", 1)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertTrue(body["ok"])
        self.assertEqual(row.config["webhook_secret_prev"], "old")
        self.assertNotEqual(row.config["webhook_secret"], "old")
        self.assertEqual(row.config["webhook_secret"], body["new_secret"])

    def test_rotate_missing_row_returns_404(self):
        school = _FakeSchool()
        with mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter"
        ) as f:
            f.return_value.first.return_value = None
            resp = im_views.rotate_webhook_secret(self._request(school), "slack", 1)
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# #5 bulk_disconnect view
# ---------------------------------------------------------------------------

class BulkDisconnectTests(SimpleTestCase):
    def _request(self, post_data=None):
        req = RequestFactory().post("/integrations/bulk-disconnect/slack/",
                                     post_data or {})
        req.school = _FakeSchool()
        req.user = mock.Mock(is_authenticated=True, is_staff=True,
                             is_superuser=False, role="admin")
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req, "session", "session")
        setattr(req, "_messages", FallbackStorage(req))
        return req

    def test_without_confirm_warns_and_redirects(self):
        req = self._request()
        resp = im_views.bulk_disconnect(req, "slack")
        self.assertEqual(resp.status_code, 302)  # redirect to hub

    def test_with_confirm_disables_all_active_rows(self):
        req = self._request({"confirm": "YES"})
        qs = mock.Mock()
        qs.filter.return_value = qs
        qs.__iter__ = lambda self_: iter([_FakeRow(pk=1, slug="slack"),
                                          _FakeRow(pk=2, slug="slack")])
        qs.update.return_value = 2
        with mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter",
            return_value=qs,
        ):
            resp = im_views.bulk_disconnect(req, "slack")
        self.assertEqual(resp.status_code, 302)
        qs.update.assert_called_once_with(is_active=False)


# ---------------------------------------------------------------------------
# #6 CSV export
# ---------------------------------------------------------------------------

class DataInventoryCsvTests(SimpleTestCase):
    def test_csv_includes_one_row_per_integration(self):
        school = _FakeSchool()
        req = RequestFactory().get("/integrations/data-inventory.csv")
        req.school = school
        req.user = mock.Mock(is_authenticated=True, is_staff=True,
                             is_superuser=False, role="admin")
        rows = [
            _FakeRow(pk=1, slug="zoom", config={
                "refresh_token": "x", "webhook_secret": "s",
                "scopes_override": ["meeting:read"],
                "expires_at": 1_700_000_000,
            }),
            _FakeRow(pk=2, slug="slack", config={"webhook_secret": "s"}),
        ]
        qs = mock.Mock()
        qs.exclude.return_value = qs
        qs.select_related.return_value = qs
        qs.order_by.return_value = qs
        qs.iterator.return_value = iter(rows)
        with mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter",
            return_value=qs,
        ):
            resp = im_views.integrations_data_inventory_csv(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        body = resp.content.decode("utf-8")
        lines = body.strip().splitlines()
        self.assertEqual(len(lines), 3)  # header + 2 rows
        self.assertIn("zoom", body)
        self.assertIn("slack", body)
        self.assertIn("meeting:read", body)  # scopes_override surfaced


# ---------------------------------------------------------------------------
# #7 Per-tenant rate-limit override
# ---------------------------------------------------------------------------

class PerTenantRateLimitOverrideTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_override_raises_threshold(self):
        # School-specific override = 200; first 121 requests must all pass
        # (default would have failed at 121).
        school = _FakeSchool(settings={"webhook_rate_limit_per_minute": 200})
        row = _FakeRow(slug="slack", school=school)
        req = RequestFactory().post("/", REMOTE_ADDR="9.9.9.9")
        for _ in range(150):
            self.assertTrue(
                im_webhooks._rate_limit_ok(integration_id=99, request=req, row=row)
            )
        # 151st still passes (limit = 200).
        self.assertTrue(
            im_webhooks._rate_limit_ok(integration_id=99, request=req, row=row)
        )

    def test_garbage_override_falls_back_to_default(self):
        school = _FakeSchool(settings={"webhook_rate_limit_per_minute": "not-a-number"})
        row = _FakeRow(slug="slack", school=school)
        req = RequestFactory().post("/", REMOTE_ADDR="8.8.8.8")
        for _ in range(im_webhooks.WEBHOOK_RATE_LIMIT_PER_MINUTE):
            im_webhooks._rate_limit_ok(integration_id=100, request=req, row=row)
        # 121st must fail — default applied.
        self.assertFalse(
            im_webhooks._rate_limit_ok(integration_id=100, request=req, row=row)
        )


# ---------------------------------------------------------------------------
# #8 rate_limit_check unified helper
# ---------------------------------------------------------------------------

class RateLimitCheckUnifiedTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_independent_scopes_have_independent_buckets(self):
        for _ in range(5):
            self.assertTrue(im_webhooks.rate_limit_check(
                scope="webhook", identifier="x", limit_per_minute=5
            ))
        # Webhook scope exhausted.
        self.assertFalse(im_webhooks.rate_limit_check(
            scope="webhook", identifier="x", limit_per_minute=5
        ))
        # API scope is a separate bucket.
        self.assertTrue(im_webhooks.rate_limit_check(
            scope="api", identifier="x", limit_per_minute=5
        ))

    def test_falls_open_on_cache_exception(self):
        with mock.patch("django.core.cache.cache.incr",
                        side_effect=RuntimeError("redis down")), \
             mock.patch("django.core.cache.cache.set",
                        side_effect=RuntimeError("redis down")):
            self.assertTrue(im_webhooks.rate_limit_check(
                scope="webhook", identifier="x", limit_per_minute=1
            ))


# ---------------------------------------------------------------------------
# #9 Deprecation lifecycle
# ---------------------------------------------------------------------------

class ConnectorDeprecationTests(SimpleTestCase):
    def test_deprecated_field_defaults_to_false(self):
        from apps.integrations_marketplace.connector_registry import get_connector
        self.assertFalse(get_connector("zoom").deprecated)

    def test_to_dict_includes_deprecated_field(self):
        from apps.integrations_marketplace.connector_registry import (
            Connector, get_connector,
        )
        d = get_connector("zoom").to_dict()
        self.assertIn("deprecated", d)
        self.assertFalse(d["deprecated"])

    def test_build_authorize_refuses_new_connect_to_deprecated_connector(self):
        from apps.integrations_marketplace import oauth as im_oauth
        from apps.integrations_marketplace.connector_registry import (
            Connector, get_connector,
        )

        # Use the real zoom connector but mark it deprecated for the test.
        real = get_connector("zoom")
        deprecated = Connector(
            slug=real.slug, label=real.label, category=real.category,
            auth_kind=real.auth_kind, authorize_url=real.authorize_url,
            token_url=real.token_url, default_scopes=real.default_scopes,
            deprecated=True, deprecation_note="Use the new zoom2 connector.",
        )
        school = _FakeSchool()
        with mock.patch(
            "apps.integrations_marketplace.oauth.get_connector",
            return_value=deprecated,
        ), mock.patch(
            "apps.integrations_marketplace.oauth.resolve_oauth_client_credentials",
            return_value=("cid", "csec"),
        ), mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter"
        ) as f:
            # No existing row → connect refused.
            f.return_value.exists.return_value = False
            url, diag = im_oauth.build_authorize_redirect(
                request=mock.Mock(session={}), connector_slug="zoom",
                school=school, campus=None,
            )
        self.assertIsNone(url)
        self.assertEqual(diag["reason"], "connector_deprecated")

    def test_build_authorize_allows_reconnect_when_existing_row_present(self):
        from apps.integrations_marketplace import oauth as im_oauth
        from apps.integrations_marketplace.connector_registry import (
            Connector, get_connector,
        )

        real = get_connector("zoom")
        deprecated = Connector(
            slug=real.slug, label=real.label, category=real.category,
            auth_kind=real.auth_kind, authorize_url=real.authorize_url,
            token_url=real.token_url, default_scopes=real.default_scopes,
            deprecated=True,
        )
        school = _FakeSchool()
        # `request.user.pk` ends up serialized into the OAuth state payload, so
        # the mock user needs a real pk (otherwise json.dumps blows up).
        req = mock.Mock()
        # Session needs item assignment (`session[key] = ...`) AND attribute
        # assignment (`session.modified = True`). A MagicMock supports both.
        req.session = mock.MagicMock()
        req.user = mock.Mock(pk=42)
        req.is_secure.return_value = True
        req.get_host.return_value = "app.example.com"
        with mock.patch(
            "apps.integrations_marketplace.oauth.get_connector",
            return_value=deprecated,
        ), mock.patch(
            "apps.integrations_marketplace.oauth.resolve_oauth_client_credentials",
            return_value=("cid", "csec"),
        ), mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter"
        ) as f:
            f.return_value.exists.return_value = True  # existing row
            url, diag = im_oauth.build_authorize_redirect(
                request=req, connector_slug="zoom",
                school=school, campus=None,
            )
        # Allowed — reconnect of existing deprecated row.
        self.assertIsNotNone(url)
        self.assertEqual(diag["reason"], "ok")


# ---------------------------------------------------------------------------
# #10 Bulk pre-stage manager view
# ---------------------------------------------------------------------------

class ManagerBulkPrestageTests(SimpleTestCase):
    def _request(self, post_data):
        req = RequestFactory().post("/manager/integrations-bulk-prestage/",
                                    post_data)
        req.user = mock.Mock(is_authenticated=True, is_staff=True,
                             is_superuser=True, role="superadmin")
        return req

    def test_missing_connector_returns_400(self):
        req = self._request({"school_ids": "1 2"})
        resp = im_manager.manager_bulk_prestage(req)
        self.assertEqual(resp.status_code, 400)

    def test_non_oauth_connector_returns_400(self):
        req = self._request({"connector_slug": "mailgun", "school_ids": "1"})
        resp = im_manager.manager_bulk_prestage(req)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not OAuth", json.loads(resp.content)["error"])

    def test_creates_pending_rows_and_skips_existing(self):
        req = self._request({"connector_slug": "zoom", "school_ids": "1 2"})
        school_a = _FakeSchool(pk=1, name="A")
        school_b = _FakeSchool(pk=2, name="B")
        existing_row = mock.Mock(pk=999)
        created_row = mock.Mock(pk=12345)

        # ServiceIntegration .filter chain: school_a has existing row, school_b doesn't.
        def filter_side_effect(*args, **kwargs):
            school = kwargs.get("school")
            f = mock.Mock()
            f.first.return_value = existing_row if school is school_a else None
            return f

        with mock.patch(
            "apps.schools.models.School.objects.filter",
            return_value=[school_a, school_b],  # iterable directly
        ), mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.filter",
            side_effect=filter_side_effect,
        ), mock.patch(
            "apps.siteconfig.models_platform_catalog.ServiceIntegration.objects.create",
            return_value=created_row,
        ):
            resp = im_manager.manager_bulk_prestage(req)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertTrue(body["ok"])
        self.assertEqual(len(body["created"]), 1)
        self.assertEqual(len(body["skipped"]), 1)
        self.assertEqual(body["created"][0]["school_id"], 2)
        self.assertEqual(body["skipped"][0]["school_id"], 1)


# ---------------------------------------------------------------------------
# Verify webhook _verify accepts rotated prev secret during grace window
# ---------------------------------------------------------------------------

class WebhookVerifyAcceptsPrevSecretTests(SimpleTestCase):
    def test_prev_secret_accepted_after_rotation(self):
        import hashlib
        import hmac as _hmac

        prev_secret = "old"
        new_secret = "new"
        row = _FakeRow(slug="slack", config={
            "webhook_secret": new_secret,
            "webhook_secret_prev": prev_secret,
        })
        # Sign body+timestamp with the OLD secret (upstream hasn't updated yet).
        ts = str(int(time.time()))
        body = b'{"event":"x"}'
        base = f"v0:{ts}:".encode("utf-8") + body
        sig = "v0=" + _hmac.new(prev_secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
        fake_req = mock.Mock(
            META={"HTTP_X_SLACK_SIGNATURE": sig,
                  "HTTP_X_SLACK_REQUEST_TIMESTAMP": ts},
            headers={"X-Slack-Signature": sig,
                     "X-Slack-Request-Timestamp": ts},
            body=body,
        )
        ok, reason = im_webhooks._verify(request=fake_req, row=row)
        self.assertTrue(ok)
        self.assertEqual(reason, "ok_via_prev_secret")

    def test_unknown_secret_rejected_even_with_prev_set(self):
        import hashlib
        import hmac as _hmac

        row = _FakeRow(slug="slack", config={
            "webhook_secret": "new", "webhook_secret_prev": "old",
        })
        ts = str(int(time.time()))
        body = b'{}'
        base = f"v0:{ts}:".encode("utf-8") + body
        # Sign with a third secret — neither matches.
        sig = "v0=" + _hmac.new(b"unrelated", base, hashlib.sha256).hexdigest()
        fake_req = mock.Mock(
            META={"HTTP_X_SLACK_SIGNATURE": sig,
                  "HTTP_X_SLACK_REQUEST_TIMESTAMP": ts},
            headers={"X-Slack-Signature": sig,
                     "X-Slack-Request-Timestamp": ts},
            body=body,
        )
        ok, reason = im_webhooks._verify(request=fake_req, row=row)
        self.assertFalse(ok)
