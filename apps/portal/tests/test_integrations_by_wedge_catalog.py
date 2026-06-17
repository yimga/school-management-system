"""Seal: the integrations-by-wedge surface reads the REAL connector SOTs.

Before this, ``integrations_by_wedge`` imported a phantom ``Connector`` ORM
model from ``apps.integrations_marketplace.models`` that never existed, so a
broad ``except`` silently pinned the page to a hardcoded 10-row stub catalog
(Canvas/Moodle/azure-ad/twilio/…). These tests assert the catalog is now
assembled from the real ``connector_registry`` + ``lms_supported_providers``
SOTs and that the wedge facet filter narrows to the correct domain.

Hermetic: the catalog builder + ``wedge()`` lookup are pure-Python, and the
JSON export path (``?format=json``) returns a ``JsonResponse`` without
rendering templates — so no DB / context processors are touched.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase

from apps.integrations_marketplace import lms_supported_providers as lms_sot
from apps.portal.views_wedge_surfaces import (
    _integration_catalog_rows,
    integrations_by_wedge,
)


def _staff_request(rf: RequestFactory, query: str = ""):
    req = rf.get("/portal/super/wedges/integrations/" + query)
    # staff_member_required only inspects is_active + is_staff.
    req.user = SimpleNamespace(
        is_active=True, is_staff=True, is_authenticated=True, is_superuser=True
    )
    return req


class IntegrationCatalogBuilderTests(SimpleTestCase):
    def test_catalog_derives_from_real_sots(self):
        rows = _integration_catalog_rows()
        slugs = {r["slug"] for r in rows}
        # Real hub connectors — absent under the old hardcoded stub.
        self.assertIn("zoom", slugs)
        self.assertIn("mailgun", slugs)
        self.assertIn("slack", slugs)
        # Real per-vendor LMS providers from the LMS SOT.
        self.assertIn("canvas", slugs)
        self.assertIn("schoology", slugs)
        # Far richer than the old 10-row fallback.
        self.assertGreater(len(rows), 20)

    def test_rows_carry_template_keys_and_contiguous_ids(self):
        rows = _integration_catalog_rows()
        for r in rows:
            self.assertLessEqual({"id", "slug", "name", "category", "vendor"}, set(r))
        self.assertEqual([r["id"] for r in rows], list(range(1, len(rows) + 1)))

    def test_no_phantom_stub_slugs(self):
        # The old static fallback invented slugs that exist in no SOT.
        slugs = {r["slug"] for r in _integration_catalog_rows()}
        self.assertNotIn("azure-ad", slugs)
        self.assertNotIn("twilio", slugs)
        self.assertNotIn("google-classroom", slugs)  # hyphen form was the stub's

    def test_slugs_are_unique(self):
        slugs = [r["slug"] for r in _integration_catalog_rows()]
        self.assertEqual(len(slugs), len(set(slugs)))


class IntegrationWedgeFacetTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _json(self, query: str):
        resp = integrations_by_wedge(_staff_request(self.rf, query))
        self.assertEqual(resp.status_code, 200)
        return json.loads(resp.content)

    def test_lms_wedge_narrows_to_lms_category(self):
        data = self._json("?wedge=2&format=json")
        self.assertTrue(data["success"])
        self.assertTrue(data["rows"])
        self.assertTrue(all(r["category"] == "lms" for r in data["rows"]))
        self.assertIn("Canvas LMS", {r["name"] for r in data["rows"]})

    def test_identity_wedge_surfaces_clever_and_classlink(self):
        data = self._json("?wedge=44&format=json")
        slugs = {r["slug"] for r in data["rows"]}
        self.assertIn(lms_sot.PROVIDER_CLEVER, slugs)
        self.assertIn(lms_sot.PROVIDER_CLASSLINK, slugs)
        self.assertTrue(all(r["category"] == "identity" for r in data["rows"]))

    def test_unfiltered_returns_full_catalog(self):
        data = self._json("?format=json")
        self.assertIsNone(data["wedge"])
        self.assertEqual(data["count"], len(_integration_catalog_rows()))

    def test_lms_and_identity_wedges_are_disjoint(self):
        lms_slugs = {r["slug"] for r in self._json("?wedge=2&format=json")["rows"]}
        ident_slugs = {r["slug"] for r in self._json("?wedge=45&format=json")["rows"]}
        self.assertFalse(lms_slugs & ident_slugs)
