"""Versioned public API manifest (§0.3 pillar 4 — contract surface).

Integrator discovery: ``endpoints`` lists a **curated** subset of named ``api_v1`` routes
(``MANIFEST_CURATED_API_V1_URL_NAMES``) plus stable non-v1 URLs (health, schema, docs,
``api:interop-edfi`` / ``api:interop-ceds`` / ``api:interop-district-readiness-sample``).
Curated routes that include path parameters use ``MANIFEST_CURATED_API_V1_REVERSE_KWARGS``
(stable placeholder UUIDs) so ``reverse`` succeeds for discovery URLs only—callers substitute
real tenant ids at runtime.
Routes that exist only for internal or staff flows may be **omitted** from the manifest;
the **full** set of ``api_v1:`` pattern names is gate-checked by
``scripts/verify_api_v1_named_routes_snapshot.py`` against ``scripts/generated/api_v1_named_routes.json``.
"""

from __future__ import annotations

import uuid

from django.http import JsonResponse
from django.urls import reverse

from apps.api.deprecation import build_deprecation_manifest_block
from apps.siteconfig.billing_sku_registry import manifest_plan_entitlements_block

# Placeholder tenant id for curated routes that include ``<uuid:id>`` (discovery template only).
_MANIFEST_PLACEHOLDER_TENANT_UUID = uuid.UUID("00000000-0000-0000-0000-000000000042")
_MANIFEST_PLACEHOLDER_STUDENT_GLOBAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
_MANIFEST_PLACEHOLDER_RECORD_ID = "00000000-0000-0000-0000-000000000001"

# Optional ``reverse(..., kwargs=…)`` for curated names whose patterns include path parameters.
MANIFEST_CURATED_API_V1_REVERSE_KWARGS: dict[str, dict[str, uuid.UUID | str]] = {
    "tenants-modules": {"id": _MANIFEST_PLACEHOLDER_TENANT_UUID},
    "student-passport": {"global_id": _MANIFEST_PLACEHOLDER_STUDENT_GLOBAL_ID},
    "students-detail": {"id": _MANIFEST_PLACEHOLDER_RECORD_ID},
    "teachers-detail": {"pk": _MANIFEST_PLACEHOLDER_RECORD_ID},
    "guardians-detail": {"pk": _MANIFEST_PLACEHOLDER_RECORD_ID},
    "evaluations-detail": {"pk": _MANIFEST_PLACEHOLDER_RECORD_ID},
    "invoices-detail": {"pk": _MANIFEST_PLACEHOLDER_RECORD_ID},
    "payments-detail": {"pk": _MANIFEST_PLACEHOLDER_RECORD_ID},
}

# Curated v1 discovery entries: JSON object key → ``api_v1`` URL pattern ``name`` (see ``urls_v1.py``).
# Additive only; ``test_manifest_curated_endpoints_align_with_reverse`` fails on rename drift.
MANIFEST_CURATED_API_V1_URL_NAMES: tuple[tuple[str, str], ...] = (
    ("me_schools", "me-schools"),
    ("me_switch_school", "me-switch-school"),
    ("tenants_children", "tenants-children"),
    ("tenants_provision", "tenants-provision"),
    ("tenants_modules", "tenants-modules"),
    ("enrollment_apply", "enrollment-apply"),
    ("enrollment_forecast", "enrollment-forecast"),
    ("attendance_bulk", "attendance-bulk"),
    ("attendance_export", "attendance-export"),
    ("scheduler_validate", "scheduler-validate"),
    ("syllabus_pacing", "syllabus-pacing"),
    ("config_education_dna", "config-education-dna"),
    ("config_education_templates", "config-education-templates"),
    ("config_integration_catalog", "config-integration-catalog"),
    ("config_risk_thresholds", "config-risk-thresholds"),
    ("reports_scheduled", "reports-scheduled-list"),
    ("reports_regulatory_presets", "reports-regulatory-presets"),
    ("reports_adhoc", "reports-adhoc-list-create"),
    ("reports_emis_prepare", "reports-emis-prepare"),
    ("finance_disputes", "finance-disputes-list"),
    ("finance_wallet_top_up", "finance-wallet-top-up"),
    ("intervention_red_flags", "intervention-red-flags"),
    ("rosetta_scales", "rosetta-scales"),
    ("super_pulse", "super-pulse"),
    ("super_usage", "super-usage"),
    ("super_recovery_rate", "super-recovery-rate"),
    ("super_tenant_health", "super-tenant-health"),
    ("super_schools_list", "super-schools-list"),
    ("compliance_export_school", "compliance-export-school"),
    ("student_transfer", "student-transfer"),
    ("rosetta_convert", "rosetta-convert"),
    ("reports_regulatory_export", "reports-regulatory-export"),
    ("attendance_bulk_update", "attendance-bulk-update"),
    ("intervention_action_center", "intervention-action-center"),
    ("intervention_calculate_risk", "intervention-calculate-risk"),
    ("student_passport", "student-passport"),
    ("platform_integration_context", "platform-integration-context"),
    ("platform_scoped_ping", "platform-scoped-ping"),
    ("people_students", "students-list"),
    ("people_students_detail", "students-detail"),
    ("people_teachers", "teachers-list"),
    ("people_teachers_detail", "teachers-detail"),
    ("people_guardians", "guardians-list"),
    ("people_guardians_detail", "guardians-detail"),
    ("evals_evaluations", "evaluations-list"),
    ("evals_evaluations_detail", "evaluations-detail"),
    ("finance_invoices", "invoices-list"),
    ("finance_invoices_detail", "invoices-detail"),
    ("finance_payments", "payments-list"),
    ("finance_payments_detail", "payments-detail"),
)


def reverse_curated_api_v1_path(url_name: str) -> str:
    """Relative path for a curated ``api_v1`` name (placeholder kwargs when required)."""
    kws = MANIFEST_CURATED_API_V1_REVERSE_KWARGS.get(url_name)
    if kws is not None:
        return reverse(f"api_v1:{url_name}", kwargs=kws)
    return reverse(f"api_v1:{url_name}")


def curated_api_v1_discovery_urls(base: str) -> dict[str, str]:
    """Absolute URLs for curated ``api_v1`` routes (``base`` = origin without trailing slash)."""
    return {
        key: f"{base}{reverse_curated_api_v1_path(url_name)}"
        for key, url_name in MANIFEST_CURATED_API_V1_URL_NAMES
    }


def build_api_v1_manifest_data(request) -> dict:
    """Return manifest dict (shared by v1 JsonResponse and v2 extended manifest)."""
    base = request.build_absolute_uri("/").rstrip("/")
    endpoints = {
        "oneroster_v1p1": f"{base}/api/oneroster/v1p1/",
        "health": f"{base}/healthz/",
        "openapi_staff": f"{base}/api/schema/",
        "developer_public_api_doc": f"{base}/developers/api-docs/",
        "interop_edfi": f"{base}{reverse('api:interop-edfi')}",
        "interop_ceds": f"{base}{reverse('api:interop-ceds')}",
        "interop_district_readiness_sample": f"{base}{reverse('api:interop-district-readiness-sample')}",
        **curated_api_v1_discovery_urls(base),
    }
    return {
        "api": "RunMyCampus",
        "version": "1.0",
        "policy": "Non-breaking additive changes without version bump; breaking changes announced 90d via changelog.",
        # RFC 8594: machine-readable list of deprecated endpoints + their
        # sunset dates + successor URLs, so the policy above has runtime teeth.
        # The live routes also emit Deprecation/Sunset/Link headers — see
        # apps/api/deprecation.py.
        "deprecations": build_deprecation_manifest_block(request),
        "plan_entitlements": manifest_plan_entitlements_block(),
        "endpoints": endpoints,
        "webhooks": {
            "finance_payments": "POST /finance/payments/webhook/<provider>/",
            "idempotency": "Optional header Idempotency-Key; X-Webhook-Idempotency-Key on outbound",
        },
        "lti": {
            "jwks": f"{base}{reverse('lti_jwks')}",
            "configure_lti_tool_jwks_uri": "Set lti_tool_jwks_uri + lti_tool_issuer on LTI ServiceIntegration for signed id_token verify.",
        },
    }


def api_v1_manifest(request):
    """Discovery for integrators: stable paths and deprecation policy."""
    return JsonResponse(build_api_v1_manifest_data(request))
