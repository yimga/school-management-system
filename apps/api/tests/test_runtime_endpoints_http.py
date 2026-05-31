"""v4.00.6 — HTTP-level coverage for the 5 /api/v1/runtime/* endpoints.

Anchors the SLA at the request boundary: every endpoint MUST return
``Surrogate-Key`` + ``Cache-Control`` headers on a 200 with a JSON body.
Without these, the Cloudflare Worker can't selectively purge per-tenant
buckets when ``RuntimeDefaults`` / ``SiteSettings`` change.

Uses ``RequestFactory`` so we exercise the view callable directly and
don't depend on the full URL conf resolving — keeps the test fast +
isolated from environment-specific middleware ordering.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.api.runtime_endpoints import (
    feature_flags_runtime,
    grading_matrix_runtime,
    runtime_defaults_snapshot,
    school_calendar_runtime,
    site_settings_snapshot,
    structural_options_runtime,
)


def _mocked_manager_empty():
    """Return a chainable QuerySet-like mock that yields no rows."""
    mgr = mock.MagicMock()
    mgr.all.return_value = mgr
    mgr.filter.return_value = mgr
    mgr.order_by.return_value = mgr
    mgr.first.return_value = None
    mgr.__getitem__.return_value = []
    mgr.__iter__ = lambda self: iter([])
    return mgr

_HANDLERS = [
    ("calendar", school_calendar_runtime),
    ("grading_matrix", grading_matrix_runtime),
    ("defaults", runtime_defaults_snapshot),
    ("site_settings", site_settings_snapshot),
    ("feature_flags", feature_flags_runtime),
]


class RuntimeEndpointHeaderContractTests(SimpleTestCase):
    """The 5 endpoints MUST stamp Surrogate-Key + return JSON."""

    def setUp(self):
        self.factory = RequestFactory(HTTP_X_RMC_VIEWPORT="A")
        # The endpoints lazily import models from other apps and then query the
        # DB. SimpleTestCase forbids DB; patch each ORM seam so the handlers
        # exercise the header / serialization paths without touching a DB.
        self._patches = [
            mock.patch("apps.academics.models.AcademicTerm.objects", _mocked_manager_empty()),
            mock.patch("apps.platform_runtime.models.RuntimeDefaults.objects", _mocked_manager_empty()),
            mock.patch("apps.siteconfig.models.SiteSettings.objects", _mocked_manager_empty()),
            mock.patch(
                "apps.policies.resolver.get_effective_policy",
                return_value={"grading": {"preset_key": "american"}},
            ),
            mock.patch(
                "apps.registries.grade_scale_resolver.resolve_grade_scale_for_tenant",
                return_value=None,
            ),
        ]
        for p in self._patches:
            try:
                p.start()
                self.addCleanup(p.stop)
            except (AttributeError, ModuleNotFoundError):
                # Model not importable in this build — endpoint already handles via ImportError.
                pass

    def _request(self, path: str):
        request = self.factory.get(path)
        school_id = uuid.uuid4()
        request.school = SimpleNamespace(
            id=school_id,
            pk=school_id,
            slug="acme-school",
            subdomain="acme",
            settings={
                "grading_scale": [{"label": "A", "min": 90}],
                "grading_passing_threshold": 60,
            },
            features={"voice_input": True},
        )
        return request

    def test_every_runtime_endpoint_returns_surrogate_key(self):
        for name, handler in _HANDLERS:
            with self.subTest(endpoint=name):
                request = self._request(f"/api/v1/runtime/{name}")
                response = handler(request)
                self.assertEqual(response.status_code, 200)
                self.assertIn("Surrogate-Key", response, f"{name} missing Surrogate-Key")
                surrogate = response["Surrogate-Key"]
                self.assertIn("acme-school", surrogate)
                self.assertIn("v=A", surrogate)

    def test_every_runtime_endpoint_returns_cache_control(self):
        for name, handler in _HANDLERS:
            with self.subTest(endpoint=name):
                request = self._request(f"/api/v1/runtime/{name}")
                response = handler(request)
                cc = response.get("Cache-Control", "")
                self.assertIn("max-age", cc)
                self.assertIn("s-maxage", cc)

    def test_every_runtime_endpoint_returns_json(self):
        for name, handler in _HANDLERS:
            with self.subTest(endpoint=name):
                request = self._request(f"/api/v1/runtime/{name}")
                response = handler(request)
                self.assertEqual(response["Content-Type"], "application/json")

    def test_viewport_header_lands_in_surrogate_key(self):
        for viewport in ("A", "B", "C"):
            factory = RequestFactory(HTTP_X_RMC_VIEWPORT=viewport)
            request = factory.get("/api/v1/runtime/calendar")
            sid = uuid.uuid4()
            request.school = SimpleNamespace(
                id=sid,
                pk=sid,
                slug="acme-school",
                subdomain="acme",
                settings={},
                features={},
            )
            response = school_calendar_runtime(request)
            self.assertIn(f"v={viewport}", response["Surrogate-Key"])

    def test_missing_viewport_defaults_to_a(self):
        request = RequestFactory().get("/api/v1/runtime/calendar")
        request.school = SimpleNamespace(slug="acme", subdomain="acme",
                                         settings={}, features={})
        response = school_calendar_runtime(request)
        self.assertIn("v=A", response["Surrogate-Key"])

    def test_missing_school_falls_back_to_host(self):
        request = RequestFactory().get("/api/v1/runtime/calendar")
        request.school = None
        # RequestFactory defaults to testserver; that's the host we expect.
        response = school_calendar_runtime(request)
        self.assertIn("testserver", response["Surrogate-Key"])

    def test_grading_matrix_projects_school_settings(self):
        request = self._request("/api/v1/runtime/grading-matrix")
        with mock.patch(
            "apps.policies.resolver.get_effective_policy",
            return_value={"grading": {"preset_key": "west_african_waec"}},
        ), mock.patch(
            "apps.registries.grade_scale_resolver.resolve_grade_scale_for_tenant",
            return_value=None,
        ):
            response = grading_matrix_runtime(request)
        body = response.content.decode("utf-8")
        self.assertIn('"preset_key":"west_african_waec"', body)
        self.assertIn('"scale"', body)

    def test_structural_options_returns_country_pack(self):
        request = RequestFactory(HTTP_X_RMC_VIEWPORT="A").get(
            "/api/v1/runtime/structural-options?country=CM"
        )
        request.school = None
        response = structural_options_runtime(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Surrogate-Key", response)
        body = response.content.decode("utf-8")
        self.assertIn('"country_code":"CM"', body)
        self.assertIn('"school_types"', body)
        self.assertIn('"grading_preset_key"', body)

    def test_feature_flags_projects_school_features(self):
        request = self._request("/api/v1/runtime/feature-flags")
        response = feature_flags_runtime(request)
        body = response.content.decode("utf-8")
        self.assertIn('"voice_input":true', body)

    def test_response_is_get_only(self):
        # All endpoints use @require_safe — POST should 405.
        for name, handler in _HANDLERS:
            with self.subTest(endpoint=name):
                request = RequestFactory(HTTP_X_RMC_VIEWPORT="A").post(f"/api/v1/runtime/{name}")
                request.school = None
                response = handler(request)
                self.assertEqual(response.status_code, 405)

    def test_head_requests_still_stamp_headers(self):
        # @require_safe allows HEAD. Body is empty per HTTP spec but headers stay.
        for name, handler in _HANDLERS:
            with self.subTest(endpoint=name):
                request = self._request(f"/api/v1/runtime/{name}")
                request.method = "HEAD"
                response = handler(request)
                self.assertEqual(response.status_code, 200)
                self.assertIn("Surrogate-Key", response)
