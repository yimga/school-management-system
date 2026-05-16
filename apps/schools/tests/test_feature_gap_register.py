"""Feature Gap Register: SOT integrity tests.

Every `status="shipped"` row MUST have a proof that resolves. Drift here is
the master prompt's "we promise it, we don't ship it" risk. These tests fail
if anyone removes a feature without flagging it `planned` or `in_progress`.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.schools.feature_gap_register import (
    FEATURE_REGISTER,
    feature_slugs,
    get_feature,
    iter_features,
)


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class FeatureGapRegisterTests(TestCase):
    def test_slugs_are_unique(self):
        slugs = [f.feature_slug for f in FEATURE_REGISTER]
        self.assertEqual(len(slugs), len(set(slugs)), "Duplicate feature_slug in register")

    def test_status_values_are_valid(self):
        valid = {"shipped", "in_progress", "planned"}
        for f in iter_features():
            self.assertIn(f.status, valid, f"{f.feature_slug} has invalid status {f.status!r}")

    def test_shipped_features_have_a_proof_source(self):
        for f in iter_features():
            if f.status != "shipped":
                continue
            has_proof = bool(
                f.proof_route_name
                or f.proof_model
                or f.proof_management_command
                or f.proof_ci_gate
            )
            self.assertTrue(
                has_proof,
                f"{f.feature_slug} is shipped but declares no proof source.",
            )

    def test_shipped_route_proofs_actually_resolve(self):
        urlconfs = ("config.urls", "config.tenant_urls", "config.manager_urls")
        for f in iter_features():
            if f.status != "shipped" or not f.proof_route_name:
                continue
            resolved_in = None
            for uc in urlconfs:
                try:
                    reverse(f.proof_route_name, urlconf=uc)
                    resolved_in = uc
                    break
                except NoReverseMatch:
                    continue
            self.assertIsNotNone(
                resolved_in,
                f"{f.feature_slug} claims proof_route_name={f.proof_route_name!r} "
                "but it doesn't resolve on any urlconf (tenant/manager/root). "
                "Either ship the route or flip status to 'in_progress'.",
            )

    def test_shipped_model_proofs_load(self):
        for f in iter_features():
            if f.status != "shipped" or not f.proof_model:
                continue
            try:
                app_label, model_name = f.proof_model.split(".", 1)
                django_apps.get_model(app_label, model_name)
            except (LookupError, ValueError) as e:
                self.fail(
                    f"{f.feature_slug} proof_model={f.proof_model!r} does not load: {e}"
                )

    def test_get_feature_known_slug(self):
        self.assertIsNotNone(get_feature("ai-center"))
        self.assertIsNone(get_feature("does-not-exist"))

    def test_known_pillar_features_present(self):
        keys = feature_slugs()
        for required in (
            "ai-center",
            "api-center",
            "studio-os-shell",
            "role-permission-matrix",
            "first-school-readiness-preflight",
            "first-school-operating-proof",
        ):
            self.assertIn(required, keys, f"Missing pillar feature {required!r}")
