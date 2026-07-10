"""Metric #20 — RFC 8594 API deprecation/sunset signalling.

Proves the producer (registry + header applier + manifest block) AND the three
appliers (Django-View mixin — live on the two superseded ``/api/rosetta/*``
routes — the DRF ``finalize_response`` mixin, and the function-view decorator).

FAILS BEFORE the wave / PASSES AFTER:
  * the header tests would fail because the routes emitted no
    ``Deprecation``/``Sunset``/``Link`` headers;
  * the manifest test would fail because ``/api/v1/manifest.json`` had no
    ``deprecations`` block.
"""

from __future__ import annotations

from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.views import View
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.api.deprecation import (
    DEPRECATED_ENDPOINTS,
    DeprecationHeaderMixin,
    DeprecationHeaderViewMixin,
    apply_deprecation_headers,
    build_deprecation_manifest_block,
    deprecated_endpoint,
    get_deprecation_spec,
    imf_fixdate,
)


class ImfFixdateTests(SimpleTestCase):
    def test_iso_date_to_imf_fixdate(self):
        # RFC 7231 IMF-fixdate, midnight GMT.
        self.assertEqual(imf_fixdate("2026-07-10"), "Fri, 10 Jul 2026 00:00:00 GMT")

    def test_bad_date_returns_none(self):
        self.assertIsNone(imf_fixdate("not-a-date"))
        self.assertIsNone(imf_fixdate(""))
        self.assertIsNone(imf_fixdate(None))


class RegistryIntegrityTests(SimpleTestCase):
    def test_registry_is_non_empty(self):
        self.assertTrue(DEPRECATED_ENDPOINTS)

    def test_sunset_strictly_after_deprecation(self):
        for spec in DEPRECATED_ENDPOINTS.values():
            self.assertLess(
                spec.deprecation_date,
                spec.sunset_date,
                msg=f"{spec.endpoint_id}: sunset must be after deprecation",
            )

    def test_dates_parse_to_imf_fixdate(self):
        for spec in DEPRECATED_ENDPOINTS.values():
            self.assertIsNotNone(imf_fixdate(spec.deprecation_date))
            self.assertIsNotNone(imf_fixdate(spec.sunset_date))

    def test_successor_url_name_reverses(self):
        for spec in DEPRECATED_ENDPOINTS.values():
            # reverse() must resolve — proves the successor route really exists.
            self.assertTrue(reverse(spec.successor_url_name))

    def test_get_spec_unknown_id_is_none(self):
        self.assertIsNone(get_deprecation_spec("nope"))
        self.assertIsNone(get_deprecation_spec(None))
        self.assertIsNone(get_deprecation_spec(""))


class ApplyHeadersTests(SimpleTestCase):
    def _spec(self):
        return get_deprecation_spec("api.rosetta.scales")

    def test_stamps_all_rfc8594_headers(self):
        resp = HttpResponse()
        apply_deprecation_headers(resp, self._spec())
        self.assertEqual(resp["Deprecation"], "Fri, 10 Jul 2026 00:00:00 GMT")
        self.assertEqual(resp["Sunset"], "Sat, 10 Jul 2027 00:00:00 GMT")
        link = resp["Link"]
        self.assertIn('rel="successor-version"', link)
        self.assertIn("/api/v1/rosetta/scales", link)
        self.assertIn('rel="deprecation"', link)
        self.assertIn("docs.runmycampus.com/deprecations/", link)

    def test_none_spec_and_none_response_are_noops(self):
        # Must never raise; returns the object unchanged.
        self.assertIsNone(apply_deprecation_headers(None, self._spec()))
        resp = HttpResponse()
        apply_deprecation_headers(resp, None)
        self.assertNotIn("Deprecation", resp)

    def test_existing_link_header_is_preserved(self):
        resp = HttpResponse()
        resp["Link"] = '<https://x/>; rel="self"'
        apply_deprecation_headers(resp, self._spec())
        self.assertIn('rel="self"', resp["Link"])
        self.assertIn('rel="successor-version"', resp["Link"])

    def test_manifest_block_shape(self):
        block = build_deprecation_manifest_block()
        self.assertTrue(block)
        ids = {row["endpoint"] for row in block}
        self.assertIn("api.rosetta.scales", ids)
        self.assertIn("api.rosetta.convert", ids)
        for row in block:
            for key in ("endpoint", "deprecation", "sunset", "successor", "documentation"):
                self.assertIn(key, row)


# ── Applier: Django-View mixin (isolated, no routing) ────────────────────────
class _DummyDjangoView(DeprecationHeaderViewMixin, View):
    deprecation_endpoint_id = "api.rosetta.scales"

    def get(self, request):
        return JsonResponse({"ok": True})


class _UnregisteredDjangoView(DeprecationHeaderViewMixin, View):
    deprecation_endpoint_id = "not.registered"

    def get(self, request):
        return JsonResponse({"ok": True})


class DjangoViewMixinTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_mixin_stamps_headers(self):
        resp = _DummyDjangoView.as_view()(self.rf.get("/x"))
        self.assertIn("Deprecation", resp)
        self.assertIn("Sunset", resp)
        self.assertIn('rel="successor-version"', resp["Link"])

    def test_unregistered_id_stamps_nothing(self):
        resp = _UnregisteredDjangoView.as_view()(self.rf.get("/x"))
        self.assertNotIn("Deprecation", resp)


# ── Applier: DRF finalize_response mixin ─────────────────────────────────────
class _DummyDRFView(DeprecationHeaderMixin, APIView):
    permission_classes = []  # unauthenticated OK for header proof
    deprecation_endpoint_id = "api.rosetta.convert"

    def get(self, request):
        return Response({"ok": True})


class DRFMixinTests(SimpleTestCase):
    def setUp(self):
        self.arf = APIRequestFactory()

    def test_drf_mixin_stamps_headers(self):
        resp = _DummyDRFView.as_view()(self.arf.get("/x"))
        self.assertIn("Deprecation", resp)
        self.assertIn("Sunset", resp)
        self.assertIn("/api/v1/rosetta/convert", resp["Link"])


# ── Applier: function-view decorator ─────────────────────────────────────────
class DecoratorTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_decorator_stamps_headers(self):
        @deprecated_endpoint("api.rosetta.scales")
        def view(request):
            return HttpResponse("hi")

        resp = view(self.rf.get("/x"))
        self.assertIn("Deprecation", resp)
        self.assertIn('rel="successor-version"', resp["Link"])


# ── Integration: live routes + manifest ──────────────────────────────────────
class LiveRouteDeprecationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dep_probe", password="testpass123", role=User.Role.ADMIN
        )

    def test_deprecated_rosetta_scales_emits_headers(self):
        self.client.force_login(self.user)
        r = self.client.get("/api/rosetta/scales/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Deprecation"], "Fri, 10 Jul 2026 00:00:00 GMT")
        self.assertEqual(r["Sunset"], "Sat, 10 Jul 2027 00:00:00 GMT")
        self.assertIn('rel="successor-version"', r["Link"])
        self.assertIn("/api/v1/rosetta/scales", r["Link"])

    def test_manifest_is_not_deprecated_no_headers(self):
        # Targeting proof: a non-deprecated endpoint carries no headers.
        r = self.client.get("/api/v1/manifest.json")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("Deprecation", r)
        self.assertNotIn("Sunset", r)

    def test_manifest_exposes_machine_readable_deprecations(self):
        r = self.client.get("/api/v1/manifest.json")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("deprecations", data)
        block = data["deprecations"]
        self.assertTrue(block)
        by_id = {row["endpoint"]: row for row in block}
        self.assertIn("api.rosetta.scales", by_id)
        row = by_id["api.rosetta.scales"]
        self.assertIn("/api/v1/rosetta/scales", row["successor"])
        self.assertEqual(row["sunset"], "2027-07-10")
