"""Connector registry SOT — every registered connector has the right shape."""

from __future__ import annotations

import os
from unittest import mock

from django.test import SimpleTestCase

from apps.integrations_marketplace.connector_registry import (
    AUTH_KIND_API_KEY,
    AUTH_KIND_OAUTH2,
    AUTH_KIND_SMTP,
    AUTH_KIND_WEBHOOK,
    CATEGORY_LABELS,
    Connector,
    get_connector,
    list_connectors,
    list_connectors_by_category,
    list_oauth_connectors,
    list_transactional_mail_connectors,
    resolve_oauth_client_credentials,
)


class ConnectorRegistryShapeTests(SimpleTestCase):
    def test_registry_is_non_empty(self):
        self.assertGreater(len(list_connectors()), 10)

    def test_every_oauth_connector_has_endpoints_and_scopes(self):
        for c in list_oauth_connectors():
            with self.subTest(slug=c.slug):
                self.assertTrue(c.authorize_url, f"{c.slug} missing authorize_url")
                self.assertTrue(c.token_url, f"{c.slug} missing token_url")
                self.assertGreater(
                    len(c.default_scopes), 0, f"{c.slug} missing default scopes"
                )

    def test_every_transactional_mail_connector_declares_anymail_backend(self):
        connectors = list_transactional_mail_connectors()
        self.assertGreater(len(connectors), 5)
        for c in connectors:
            with self.subTest(slug=c.slug):
                self.assertTrue(
                    c.anymail_backend,
                    f"{c.slug} missing anymail_backend dotted path",
                )

    def test_categories_are_known(self):
        for c in list_connectors():
            with self.subTest(slug=c.slug):
                self.assertIn(c.category, CATEGORY_LABELS)

    def test_auth_kinds_are_known(self):
        valid = {AUTH_KIND_OAUTH2, AUTH_KIND_API_KEY, AUTH_KIND_SMTP, AUTH_KIND_WEBHOOK}
        for c in list_connectors():
            with self.subTest(slug=c.slug):
                self.assertIn(c.auth_kind, valid)

    def test_get_connector_is_case_insensitive(self):
        self.assertIsNotNone(get_connector("ZOOM"))
        self.assertIsNotNone(get_connector("Zoom"))
        self.assertIsNone(get_connector(""))
        self.assertIsNone(get_connector("nope-not-registered"))

    def test_listing_by_category_groups_expected_slugs(self):
        grouped = list_connectors_by_category()
        meeting_slugs = {c.slug for c in grouped.get("meeting", [])}
        for expected in {"zoom", "microsoft_teams", "google_meet", "webex"}:
            self.assertIn(expected, meeting_slugs)

        chat_slugs = {c.slug for c in grouped.get("chat", [])}
        for expected in {"slack", "microsoft_teams_chat", "discord"}:
            self.assertIn(expected, chat_slugs)

    def test_to_dict_round_trips_required_keys(self):
        d = get_connector("slack").to_dict()
        for key in {"slug", "label", "category", "auth_kind", "is_oauth", "default_scopes"}:
            self.assertIn(key, d)

    def test_resolve_oauth_client_credentials_reads_env(self):
        env = {
            "INTEGRATIONS_ZOOM_CLIENT_ID": "ci-abc",
            "INTEGRATIONS_ZOOM_CLIENT_SECRET": "sec-xyz",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            cid, secret = resolve_oauth_client_credentials("zoom")
            self.assertEqual(cid, "ci-abc")
            self.assertEqual(secret, "sec-xyz")

    def test_resolve_oauth_client_credentials_returns_empty_when_unset(self):
        env = {}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("INTEGRATIONS_FAKE_CONNECTOR_CLIENT_ID", None)
            os.environ.pop("INTEGRATIONS_FAKE_CONNECTOR_CLIENT_SECRET", None)
            self.assertEqual(
                resolve_oauth_client_credentials("fake_connector"), ("", "")
            )

    def test_pkce_connectors_advertise_the_flag(self):
        self.assertTrue(get_connector("zoom").pkce)
        self.assertTrue(get_connector("microsoft_teams").pkce)
        self.assertTrue(get_connector("google_meet").pkce)
        self.assertTrue(get_connector("gmail").pkce)


class ConnectorImmutableContractTests(SimpleTestCase):
    """Anyone editing the registry must keep these guarantees."""

    def test_slugs_are_unique_lowercase_snake(self):
        slugs = [c.slug for c in list_connectors()]
        self.assertEqual(len(slugs), len(set(slugs)), "duplicate slugs")
        for slug in slugs:
            with self.subTest(slug=slug):
                self.assertEqual(slug, slug.lower())
                self.assertNotIn(" ", slug)

    def test_dataclass_is_frozen(self):
        c = get_connector("zoom")
        with self.assertRaises(Exception):
            c.label = "tampered"  # type: ignore[misc]
        self.assertIsInstance(c, Connector)
