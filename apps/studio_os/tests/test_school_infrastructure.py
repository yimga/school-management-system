# -*- coding: utf-8 -*-
"""School infrastructure registry: templates, preview API, honest apply contract."""

import json
from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from apps.studio_os.school_infrastructure import (
    build_infrastructure_preview,
    list_school_template_keys,
    load_pack_catalog_from_disk,
    validate_pack_catalog_entries,
)

from apps.studio_os.views import (
    school_infrastructure_apply_api,
    school_infrastructure_preview_api,
    school_infrastructure_validate_api,
)


def _unwrap_view(view_callable):
    f = view_callable
    while hasattr(f, "__wrapped__"):
        f = f.__wrapped__
    return f


class SchoolInfrastructureRegistryTests(SimpleTestCase):
    def test_registry_lists_five_templates(self):
        keys = list_school_template_keys()
        self.assertGreaterEqual(len(keys), 5)
        for k in (
            "private_school",
            "public_k12",
            "international_school",
            "faith_based",
            "multi_campus_group",
        ):
            self.assertIn(k, keys)

    def test_catalog_on_disk_validates(self):
        cat = load_pack_catalog_from_disk()
        w = validate_pack_catalog_entries(cat)
        self.assertEqual(w, [], msg=w)

    def test_preview_resolves_packs_for_private_school(self):
        payload = build_infrastructure_preview(None, "private_school")
        self.assertTrue(payload.get("ok"))
        self.assertFalse(payload.get("tenant_safe_apply"))
        self.assertGreater(len(payload.get("resolved_workflow_packs") or []), 0)


class SchoolInfrastructureApiContractTests(SimpleTestCase):
    """No DB: unwrap decorators and exercise view bodies (same pattern as mechanical gates)."""

    def test_urls_resolve(self):
        reverse("studio_os:school_infrastructure_preview_api")
        reverse("studio_os:school_infrastructure_validate_api")
        reverse("studio_os:school_infrastructure_apply_api")

    def test_preview_api_core_returns_payload(self):
        rf = RequestFactory()
        req = rf.get("/studio/api/school-infrastructure/preview/", {"template": "private_school"})
        req.user = SimpleNamespace(is_authenticated=True, is_staff=True)
        req.school = None
        inner = _unwrap_view(school_infrastructure_preview_api)
        resp = inner(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertIn("resolved_workflow_packs", data)
        self.assertIn("diff_rows", data)
        self.assertIn("install_preview", data)
        self.assertIn("resolved_workflow_keys", data["install_preview"])

    def test_validate_api_core_ok(self):
        rf = RequestFactory()
        req = rf.get("/studio/api/school-infrastructure/validate/", {"template": "public_k12"})
        req.user = SimpleNamespace(is_authenticated=True, is_staff=True)
        req.school = None
        inner = _unwrap_view(school_infrastructure_validate_api)
        resp = inner(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertTrue(data.get("ok"))

    def test_apply_api_returns_not_implemented(self):
        rf = RequestFactory()
        req = rf.post("/studio/api/school-infrastructure/apply/")
        req.user = SimpleNamespace(is_authenticated=True, is_staff=True)
        inner = _unwrap_view(school_infrastructure_apply_api)
        resp = inner(req)
        self.assertEqual(resp.status_code, 501)
        data = json.loads(resp.content.decode())
        self.assertFalse(data.get("supported"))
