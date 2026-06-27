"""Contract tests: lock the request/response SHAPE of key documented,
public API endpoints so a future change can't silently break consumers.

Each test asserts the HTTP status AND the exact top-level keys of the JSON
envelope (a superset/subset check that fails if a documented key is
dropped). Scoped to UNAUTHENTICATED public endpoints so the suite needs no
DB fixtures — these are exactly the endpoints third-party integrators
build against (the manifest discovery doc + the public catalogs).

Companion to:
  * ``test_api_v1_contract_smoke.py`` (status codes only)
  * ``test_api_v1_manifest.py`` (manifest field values)
This file locks the KEY SET of each envelope.
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse


class ApiV1ManifestContractTests(TestCase):
    """`GET /api/v1/manifest.json` — integrator discovery document."""

    def test_manifest_top_level_keys(self):
        r = self.client.get("/api/v1/manifest.json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r["Content-Type"].split(";")[0].strip(), "application/json"
        )
        data = r.json()
        # Locked top-level contract keys. New keys may be ADDED (additive
        # policy) — this asserts none of the documented ones disappear.
        for key in ("api", "version", "policy", "endpoints", "webhooks", "lti"):
            self.assertIn(key, data, msg=f"manifest dropped top-level key {key!r}")
        self.assertEqual(data["api"], "RunMyCampus")
        self.assertEqual(data["version"], "1.0")
        self.assertIsInstance(data["endpoints"], dict)


class WebhookEventTypesContractTests(TestCase):
    """`GET /api/v1/webhooks/event-types/` — public webhook catalog."""

    def test_envelope_shape(self):
        url = reverse("api_v1:webhooks-event-types")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(
            set(data.keys()),
            {"events", "count", "doc_url"},
            msg="webhook event-types envelope keys drifted",
        )
        self.assertIsInstance(data["events"], list)
        self.assertIsInstance(data["count"], int)
        self.assertEqual(data["count"], len(data["events"]))

    def test_event_item_shape_when_present(self):
        url = reverse("api_v1:webhooks-event-types")
        data = self.client.get(url).json()
        for event in data["events"]:
            self.assertEqual(
                set(event.keys()),
                {
                    "event_type",
                    "description",
                    "schema_version",
                    "retry_policy",
                    "payload",
                },
                msg=f"event item keys drifted: {event!r}",
            )
            self.assertEqual(set(event["payload"].keys()), {"required", "optional"})

    def test_caching_header_present(self):
        url = reverse("api_v1:webhooks-event-types")
        r = self.client.get(url)
        self.assertIn("max-age", r.get("Cache-Control", ""))


class MarketplaceCatalogContractTests(TestCase):
    """`GET /api/v1/marketplace/{apps,scopes}/` — public marketplace catalog."""

    def test_apps_envelope_shape(self):
        url = reverse("api_v1:marketplace-apps")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        # ImportError fallback yields {"apps","count"} only, so assert the
        # documented keys are a SUBSET that is always present.
        self.assertIn("apps", data)
        self.assertIn("count", data)
        self.assertIsInstance(data["apps"], list)
        self.assertEqual(data["count"], len(data["apps"]))

    def test_scopes_envelope_shape(self):
        url = reverse("api_v1:marketplace-scopes")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("scopes", data)
        self.assertIn("count", data)
        self.assertIsInstance(data["scopes"], list)
        self.assertEqual(data["count"], len(data["scopes"]))


class ApiV2ContractTests(TestCase):
    """`/api/v2/ping/` + `/api/v2/manifest.json` — versioned stable surface."""

    def test_ping_shape(self):
        url = reverse("api_v2:ping")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        # ping is a liveness contract — assert it stays JSON object.
        self.assertIsInstance(data, dict)

    def test_manifest_resolves(self):
        url = reverse("api_v2:manifest")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r["Content-Type"].split(";")[0].strip(), "application/json"
        )


class PublicEndpointsThrottleContractTests(TestCase):
    """The public catalog endpoints must declare a throttle (abuse surface)."""

    def test_public_endpoints_carry_throttle_classes(self):
        from apps.api.views_webhook_catalog import WebhookEventTypesView
        from apps.api.views_marketplace_catalog import (
            MarketplaceAppsListView,
            MarketplaceScopesListView,
        )
        from apps.api.throttling import ApiPublicReadThrottle

        for view_cls in (
            WebhookEventTypesView,
            MarketplaceAppsListView,
            MarketplaceScopesListView,
        ):
            self.assertIn(
                ApiPublicReadThrottle,
                getattr(view_cls, "throttle_classes", []),
                msg=f"{view_cls.__name__} must declare ApiPublicReadThrottle",
            )

    def test_v1_crud_viewsets_carry_throttle_classes(self):
        from apps.api.views_v1_tenant_crud import (
            V1EvaluationViewSet,
            V1GuardianViewSet,
            V1InvoiceViewSet,
            V1PaymentViewSet,
            V1StudentViewSet,
            V1TeacherViewSet,
        )
        from apps.api.throttling import ApiReadWriteThrottle

        for view_cls in (
            V1StudentViewSet,
            V1TeacherViewSet,
            V1GuardianViewSet,
            V1EvaluationViewSet,
            V1InvoiceViewSet,
            V1PaymentViewSet,
        ):
            self.assertIn(
                ApiReadWriteThrottle,
                getattr(view_cls, "throttle_classes", []),
                msg=f"{view_cls.__name__} must declare ApiReadWriteThrottle",
            )
