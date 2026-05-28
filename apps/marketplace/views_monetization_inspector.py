"""v4.00.13 — Monetization manifest admin inspector.

Closes the v4.00.12 follow-on gap: ``template_monetization_manifest.py``
shipped a validator + ``template_partner_manifest.py`` wires it, but
there was no operator-facing UI to inspect partner manifests through
the validator. This view renders the inspector at
``/super/marketplace/monetization-inspector/``.

Operator can paste a manifest JSON, see the validation result, and
preview the example manifest. The view never persists submitted
manifests — it's a read-only inspector.
"""

from __future__ import annotations

import json
import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)


@method_decorator(staff_member_required, name="dispatch")
class MonetizationManifestInspectorView(LoginRequiredMixin, View):
    """Staff-only inspector for partner monetization manifests.

    # rbac-allow: super-staff-monetization-manifest-inspector
    """

    template = "marketplace/monetization_inspector.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        from apps.marketplace.template_monetization_manifest import (
            ALLOWED_CURRENCIES,
            PRICING_MODELS,
            SETTLEMENT_PROVIDERS,
            example_monetization_manifest,
        )

        return render(request, self.template, {
            "example": json.dumps(example_monetization_manifest(), indent=2),
            "pricing_models": sorted(PRICING_MODELS),
            "settlement_providers": sorted(SETTLEMENT_PROVIDERS),
            "allowed_currencies": sorted(ALLOWED_CURRENCIES),
            "validation": None,
            "submitted": "",
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        from apps.marketplace.template_monetization_manifest import (
            ALLOWED_CURRENCIES,
            PRICING_MODELS,
            SETTLEMENT_PROVIDERS,
            example_monetization_manifest,
            validate_monetization_manifest,
        )

        submitted = (request.POST.get("manifest") or "").strip()
        validation: dict | None = None
        if submitted:
            try:
                parsed = json.loads(submitted)
            except (json.JSONDecodeError, ValueError) as exc:
                validation = {
                    "ok": False,
                    "findings": [f"JSON parse error: {exc}"],
                    "pricing_model": "",
                    "settlement_provider": "",
                    "rev_share_pct": 0.0,
                }
            else:
                result = validate_monetization_manifest(parsed)
                validation = {
                    "ok": result.ok,
                    "findings": list(result.findings),
                    "pricing_model": result.pricing_model,
                    "settlement_provider": result.settlement_provider,
                    "rev_share_pct": result.rev_share_pct,
                }

        return render(request, self.template, {
            "example": json.dumps(example_monetization_manifest(), indent=2),
            "pricing_models": sorted(PRICING_MODELS),
            "settlement_providers": sorted(SETTLEMENT_PROVIDERS),
            "allowed_currencies": sorted(ALLOWED_CURRENCIES),
            "validation": validation,
            "submitted": submitted,
        })
