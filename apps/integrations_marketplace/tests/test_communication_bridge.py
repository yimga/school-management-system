"""Tests for the v2.79 bridge in `apps.communication.integrations`.

This is the load-bearing piece of v2.79 — without it, every WhatsApp/Zoom send
silently used the platform-shared global credentials regardless of which tenant
had configured a row through the marketplace hub.

DB-free: we mock the resolver and Django settings so the tests run without a
test database, and so a missing `settings.ZOOM_API_KEY` in CI doesn't taint
the assertions.
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.communication import integrations as comm_integrations
from apps.communication.integrations import (
    WhatsAppIntegration,
    ZoomIntegration,
    _resolve_connector_config_safe,
)


class _FakeSchool:
    def __init__(self, name="acme"):
        self.name = name


class ResolverSafeWrapperTests(SimpleTestCase):
    def test_none_school_returns_empty_dict_without_importing_resolver(self):
        # Patch the resolver to a sentinel that would raise if invoked — proves
        # we short-circuit before the import path.
        with mock.patch(
            "apps.integrations_marketplace.resolver.resolve_connector_config",
            side_effect=AssertionError("must not be called for school=None"),
        ):
            self.assertEqual(_resolve_connector_config_safe("zoom", school=None), {})

    def test_unconfigured_row_returns_empty_dict(self):
        resolved = mock.Mock(is_configured=False, is_active=False, config={})
        with mock.patch(
            "apps.integrations_marketplace.resolver.resolve_connector_config",
            return_value=resolved,
        ):
            result = _resolve_connector_config_safe("zoom", school=_FakeSchool())
        self.assertEqual(result, {})

    def test_inactive_row_returns_empty_dict(self):
        resolved = mock.Mock(is_configured=True, is_active=False, config={"a": 1})
        with mock.patch(
            "apps.integrations_marketplace.resolver.resolve_connector_config",
            return_value=resolved,
        ):
            result = _resolve_connector_config_safe("zoom", school=_FakeSchool())
        self.assertEqual(result, {})

    def test_active_configured_row_returns_config_copy(self):
        resolved = mock.Mock(is_configured=True, is_active=True,
                             config={"access_token": "tenant-bearer"})
        with mock.patch(
            "apps.integrations_marketplace.resolver.resolve_connector_config",
            return_value=resolved,
        ):
            result = _resolve_connector_config_safe("zoom", school=_FakeSchool())
        self.assertEqual(result, {"access_token": "tenant-bearer"})

    def test_resolver_exception_is_swallowed_to_empty_dict(self):
        # The bridge MUST NOT let a broken resolver take down a send.
        with mock.patch(
            "apps.integrations_marketplace.resolver.resolve_connector_config",
            side_effect=RuntimeError("upstream broken"),
        ):
            result = _resolve_connector_config_safe("zoom", school=_FakeSchool())
        self.assertEqual(result, {})


class WhatsAppIntegrationTenantPickupTests(SimpleTestCase):
    def test_no_school_falls_back_to_settings(self):
        with mock.patch.object(comm_integrations, "settings") as s:
            s.WHATSAPP_API_TOKEN = "global-token"
            s.WHATSAPP_API_URL = "https://global"
            s.WHATSAPP_BUSINESS_NUMBER = "+global"
            wa = WhatsAppIntegration(school=None)
        self.assertEqual(wa.api_token, "global-token")
        self.assertEqual(wa.api_url, "https://global")
        self.assertEqual(wa.phone_number, "+global")

    def test_tenant_config_wins_over_global_settings(self):
        with mock.patch.object(
            comm_integrations, "_resolve_connector_config_safe",
            return_value={
                "access_token": "tenant-token",
                "api_url": "https://tenant",
                "phone_number_id": "+tenant",
            },
        ), mock.patch.object(comm_integrations, "settings") as s:
            s.WHATSAPP_API_TOKEN = "global-token"
            s.WHATSAPP_API_URL = "https://global"
            s.WHATSAPP_BUSINESS_NUMBER = "+global"
            wa = WhatsAppIntegration(school=_FakeSchool())
        self.assertEqual(wa.api_token, "tenant-token")
        self.assertEqual(wa.api_url, "https://tenant")
        self.assertEqual(wa.phone_number, "+tenant")

    def test_partial_tenant_config_falls_back_per_field(self):
        # Only access_token came from tenant; URL/phone should fall back.
        with mock.patch.object(
            comm_integrations, "_resolve_connector_config_safe",
            return_value={"access_token": "tenant-token"},
        ), mock.patch.object(comm_integrations, "settings") as s:
            s.WHATSAPP_API_TOKEN = "global-token"
            s.WHATSAPP_API_URL = "https://global"
            s.WHATSAPP_BUSINESS_NUMBER = "+global"
            wa = WhatsAppIntegration(school=_FakeSchool())
        self.assertEqual(wa.api_token, "tenant-token")
        self.assertEqual(wa.api_url, "https://global")
        self.assertEqual(wa.phone_number, "+global")


class ZoomIntegrationTenantPickupTests(SimpleTestCase):
    def test_oauth_bearer_from_tenant_wins(self):
        with mock.patch.object(
            comm_integrations, "_resolve_connector_config_safe",
            return_value={"access_token": "tenant-oauth-bearer"},
        ):
            z = ZoomIntegration(school=_FakeSchool())
        self.assertEqual(z._access_token, "tenant-oauth-bearer")
        # get_token() must short-circuit to the bearer without hitting jwt.encode.
        self.assertEqual(z.get_token(), "tenant-oauth-bearer")

    def test_no_tenant_falls_back_to_legacy_jwt_config(self):
        with mock.patch.object(
            comm_integrations, "_resolve_connector_config_safe", return_value={},
        ), mock.patch.object(comm_integrations, "settings") as s:
            s.ZOOM_API_KEY = "legacy-key"
            s.ZOOM_API_SECRET = "legacy-secret"
            z = ZoomIntegration(school=None)
        self.assertEqual(z._access_token, "")
        self.assertEqual(z.api_key, "legacy-key")
        self.assertEqual(z.api_secret, "legacy-secret")

    def test_get_token_without_bearer_uses_jwt_encode_with_api_key(self):
        with mock.patch.object(
            comm_integrations, "_resolve_connector_config_safe", return_value={},
        ), mock.patch.object(comm_integrations, "settings") as s:
            s.ZOOM_API_KEY = "kk"
            s.ZOOM_API_SECRET = "ss"
            z = ZoomIntegration(school=None)
        with mock.patch("jwt.encode", return_value="signed-jwt") as enc:
            tok = z.get_token()
        self.assertEqual(tok, "signed-jwt")
        # Issuer claim must be the api_key resolved at construction.
        args, kwargs = enc.call_args
        self.assertEqual(args[0]["iss"], "kk")
