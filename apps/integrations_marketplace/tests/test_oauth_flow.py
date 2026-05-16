"""OAuth state + token-persistence tests (no live HTTP)."""

from __future__ import annotations

import os
from unittest import mock

from django.test import RequestFactory, TestCase
from django.contrib.sessions.middleware import SessionMiddleware

from apps.integrations_marketplace.connector_registry import get_connector
from apps.integrations_marketplace.oauth import (
    build_authorize_redirect,
    build_token_exchange_payload,
    persist_oauth_tokens,
    validate_callback_state,
)


def _request_with_session(method: str = "GET", path: str = "/integrations/connect/zoom/"):
    rf = RequestFactory()
    req = getattr(rf, method.lower())(path)
    SessionMiddleware(lambda r: None).process_request(req)
    req.session.save()
    return req


class StateSigningTests(TestCase):
    def test_build_refuses_unknown_connector(self):
        req = _request_with_session()
        url, diag = build_authorize_redirect(
            request=req,
            connector_slug="not-a-real-thing",
            school=None,
        )
        self.assertIsNone(url)
        self.assertEqual(diag["reason"], "unknown_connector")

    def test_build_refuses_non_oauth_connector(self):
        # 'discord' is a webhook connector — not OAuth2.
        req = _request_with_session()
        url, diag = build_authorize_redirect(
            request=req,
            connector_slug="discord",
            school=None,
        )
        self.assertIsNone(url)
        self.assertEqual(diag["reason"], "wrong_auth_kind")

    def test_build_refuses_when_client_credentials_missing(self):
        req = _request_with_session()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("INTEGRATIONS_ZOOM_CLIENT_ID", None)
            os.environ.pop("INTEGRATIONS_ZOOM_CLIENT_SECRET", None)
            url, diag = build_authorize_redirect(
                request=req,
                connector_slug="zoom",
                school=mock.Mock(pk=1),
            )
        self.assertIsNone(url)
        self.assertEqual(diag["reason"], "missing_client_credentials")

    def test_build_returns_authorize_url_with_state_and_pkce(self):
        req = _request_with_session()
        env = {
            "INTEGRATIONS_ZOOM_CLIENT_ID": "cid",
            "INTEGRATIONS_ZOOM_CLIENT_SECRET": "secret",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            url, diag = build_authorize_redirect(
                request=req,
                connector_slug="zoom",
                school=mock.Mock(pk=42),
            )
        self.assertIsNotNone(url)
        self.assertIn("https://zoom.us/oauth/authorize", url)
        self.assertIn("client_id=cid", url)
        self.assertIn("state=", url)
        # Zoom advertises PKCE, so a challenge should be in the URL.
        self.assertIn("code_challenge=", url)
        self.assertIn("code_challenge_method=S256", url)
        self.assertEqual(diag["reason"], "ok")

    def test_callback_rejects_unsigned_state(self):
        req = _request_with_session()
        payload, diag = validate_callback_state(
            request=req, connector_slug="zoom", state="not-a-real-state"
        )
        self.assertIsNone(payload)
        self.assertEqual(diag["reason"], "bad_signature_or_expired")

    def test_callback_rejects_slug_mismatch(self):
        req = _request_with_session()
        env = {
            "INTEGRATIONS_ZOOM_CLIENT_ID": "cid",
            "INTEGRATIONS_ZOOM_CLIENT_SECRET": "secret",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            url, _ = build_authorize_redirect(
                request=req,
                connector_slug="zoom",
                school=mock.Mock(pk=42),
            )
        # Pull state out of the URL.
        from urllib.parse import parse_qs, urlsplit

        state = parse_qs(urlsplit(url).query)["state"][0]

        # Validate as 'slack' — should fail.
        payload, diag = validate_callback_state(
            request=req, connector_slug="slack", state=state
        )
        self.assertIsNone(payload)
        self.assertEqual(diag["reason"], "slug_mismatch")

    def test_callback_accepts_round_trip_state(self):
        req = _request_with_session()
        env = {
            "INTEGRATIONS_ZOOM_CLIENT_ID": "cid",
            "INTEGRATIONS_ZOOM_CLIENT_SECRET": "secret",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            url, _ = build_authorize_redirect(
                request=req,
                connector_slug="zoom",
                school=mock.Mock(pk=42),
            )
        from urllib.parse import parse_qs, urlsplit

        state = parse_qs(urlsplit(url).query)["state"][0]
        payload, diag = validate_callback_state(
            request=req, connector_slug="zoom", state=state
        )
        self.assertIsNotNone(payload)
        self.assertEqual(diag["reason"], "ok")
        self.assertEqual(payload["slug"], "zoom")
        self.assertEqual(payload["school_id"], 42)
        self.assertIn("code_verifier", payload)


class TokenPersistenceTests(TestCase):
    def test_persist_creates_service_integration_row(self):
        from apps.schools.models import School
        from apps.siteconfig.models_platform_catalog import ServiceIntegration

        school = School.objects.create(name="Persist Test")
        connector = get_connector("zoom")
        row = persist_oauth_tokens(
            connector=connector,
            school=school,
            campus=None,
            token_response={
                "access_token": "tok-1",
                "refresh_token": "ref-1",
                "scope": "meeting:write meeting:read",
                "expires_in": 3600,
            },
        )
        self.assertEqual(row.school, school)
        self.assertEqual(row.connector_slug, "zoom")
        self.assertEqual(row.service_name, "zoom")
        self.assertEqual(row.service_type, ServiceIntegration.ServiceType.OAUTH)
        self.assertEqual(row.config["access_token"], "tok-1")
        self.assertEqual(set(row.enabled_scopes), {"meeting:write", "meeting:read"})
        self.assertTrue(row.is_active)

    def test_persist_refuses_empty_access_token(self):
        from apps.schools.models import School

        school = School.objects.create(name="Persist Test 2")
        connector = get_connector("zoom")
        with self.assertRaises(ValueError):
            persist_oauth_tokens(
                connector=connector,
                school=school,
                campus=None,
                token_response={"refresh_token": "x"},
            )

    def test_persist_updates_existing_row_idempotent(self):
        from apps.schools.models import School
        from apps.siteconfig.models_platform_catalog import ServiceIntegration

        school = School.objects.create(name="Persist Test 3")
        connector = get_connector("zoom")
        for tok in ("tok-a", "tok-b", "tok-c"):
            persist_oauth_tokens(
                connector=connector,
                school=school,
                campus=None,
                token_response={"access_token": tok, "scope": "meeting:write"},
            )
        rows = ServiceIntegration.objects.filter(
            school=school, connector_slug="zoom"
        )
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().config["access_token"], "tok-c")


class TokenExchangePayloadTests(TestCase):
    def test_payload_includes_code_verifier_for_pkce_connector(self):
        req = _request_with_session()
        connector = get_connector("zoom")
        body = build_token_exchange_payload(
            request=req,
            connector=connector,
            code="auth-code",
            state_payload={"code_verifier": "v-123"},
        )
        self.assertEqual(body["grant_type"], "authorization_code")
        self.assertEqual(body["code"], "auth-code")
        self.assertEqual(body["code_verifier"], "v-123")

    def test_payload_omits_verifier_for_non_pkce_connector(self):
        req = _request_with_session()
        connector = get_connector("webex")  # webex has pkce=False
        body = build_token_exchange_payload(
            request=req,
            connector=connector,
            code="auth-code",
            state_payload={"code_verifier": "v-123"},
        )
        self.assertNotIn("code_verifier", body)
