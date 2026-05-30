"""v4.00.92-95 Studio-OS-10X Waves 2-5 — auto-emitted scaffold registry.

Each surface is a small contract callable returning a structured envelope:
``{"surface": <slug>, "wave": <int>, "pillar": <str>, "status":
"scaffold_registered", "title": <str>, "generated_at": <iso>}``.

The smoke harness verifies the contract exists + envelope shape matches.
Real runtime layers in over the 5-wave roll-out per the umbrella plan.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

PILLAR = "oneroster_demographics"
SURFACES: tuple[tuple[str, str, int], ...] = (
    ('grading_periods_delta', '/gradingPeriods/delta/', 2),
    ('terms_delta', '/terms/delta/', 2),
    ('lineitem_categories', '/lineItemCategories/', 2),
    ('score_scales_post', '/scoreScales/ POST', 2),
    ('results_bulk_post', '/results/bulk/ POST', 2),
    ('filter_regex_op', 'Filter REGEX operator (safe-subset)', 2),
    ('filter_in_list_coercion', 'Filter IN-list coercion', 2),
    ('conditional_get_last_modified', 'Conditional GET (Last-Modified)', 2),
    ('demographics_extension_hook', 'Demographics extension hook surface', 2),
    ('demographics_ell_services', 'Demographics: ellServices', 2),
    ('demographics_iep', 'Demographics: iepStatus', 2),
    ('demographics_504_plan', 'Demographics: 504PlanStatus', 2),
    ('demographics_gifted_talented', 'Demographics: giftedTalentedStatus', 2),
    ('demographics_title_1', 'Demographics: title1Status', 2),
    ('assets_api_stub', '/assets/ API stub', 3),
    ('csv_import_per_resource', 'CSV import endpoint per resource', 3),
    ('idempotency_token_ttl_surface', 'Idempotency token TTL surface', 3),
    ('validate_only_flag_on_bulk', 'validate-only flag on bulk', 3),
    ('schema_introspection_endpoint', 'Schema introspection endpoint', 3),
    ('error_taxonomy_doc', 'Error taxonomy doc', 3),
    ('deprecation_warning_header', 'Deprecation warning header', 3),
    ('sunset_header', 'Sunset header', 3),
    ('vendor_extension_hook', 'Vendor extension hook', 3),
    ('x_total_count_header', 'X-Total-Count header', 3),
    ('x_ratelimit_headers', 'X-RateLimit headers', 3),
    ('filter_date_range_macros', 'Filter date-range macros', 3),
    ('demographics_audit_trail', 'Demographics audit trail', 3),
    ('demographics_multi_residence', 'Demographics multi-residence', 3),
    ('v12_conformance_verifier', 'Full v1.2 conformance verifier', 4),
    ('schema_diff_vs_spec', 'Schema diff vs spec', 4),
    ('compatibility_matrix_doc', 'Compatibility matrix doc', 4),
    ('enrollments_tombstones', '/enrollments/ tombstones', 4),
    ('demographics_tombstones', '/demographics/ tombstones', 4),
    ('cross_resource_cascade_delete_safety', 'Cross-resource cascade-delete safety', 4),
    ('filter_type_coercion', 'Filter type coercion', 4),
    ('filter_null_vs_empty_disambig', 'Filter NULL-vs-empty disambiguation', 4),
    ('filter_quote_escape_hardening', 'Filter quote-escape hardening', 4),
    ('multivalue_field_array_semantics', 'Multi-value field array semantics', 4),
    ('ordering_stability_guarantee', 'Ordering stability guarantee', 4),
    ('page_token_opaque_encoding', 'Page token opaque encoding', 4),
    ('vendor_id_field', 'vendor-id field', 4),
    ('x_rmc_tenant_header', 'x-rmc-tenant header', 4),
    ('rfc7807_problem_details', 'RFC-7807 problem details', 5),
    ('rfc9457_error_objects', 'RFC-9457 error objects', 5),
    ('link_header_pagination', 'Link-header pagination', 5),
    ('metadata_endpoint', '/metadata/ endpoint', 5),
    ('version_endpoint', '/version/ endpoint', 5),
    ('capabilities_endpoint', '/capabilities/ endpoint', 5),
    ('openapi_3_1_schema_emitter', 'OpenAPI 3.1 schema emitter', 5),
    ('json_schema_emitter_per_resource', 'JSON-Schema emitter per resource', 5),
    ('graphql_stub_users', 'GraphQL stub for /users/', 5),
    ('scim_2_0_compat_shim', 'SCIM 2.0 compatibility shim', 5),
    ('ferpa_coppa_flag_matrix', 'FERPA/COPPA flag matrix on /demographics/', 5),
    ('gdpr_erasure_users_delete', 'GDPR erasure on /users/ DELETE', 5),
    ('age_of_digital_consent_gate', 'Age of digital consent gate', 5),
    ('tenant_data_region_pin', 'Tenant data-region pin', 5),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _make_surface(slug: str, title: str, wave: int):
    def _call(**kwargs: Any) -> dict[str, Any]:
        payload = {
            "surface": slug,
            "title": title,
            "wave": wave,
            "pillar": PILLAR,
            "status": "scaffold_registered",
            "generated_at": _now_iso(),
        }
        if kwargs:
            payload["received_kwargs_keys"] = sorted(kwargs.keys())
        return payload
    _call.__name__ = f"surface_{slug}"
    return _call


# Bind a callable per surface so callers can do
# ``getattr(module, f"surface_{slug}")()`` and get back the envelope.
_BOUND: dict[str, object] = {}
for _slug, _title, _wave in SURFACES:
    _fn = _make_surface(_slug, _title, _wave)
    _BOUND[_slug] = _fn
    globals()[f"surface_{_slug}"] = _fn
del _slug, _title, _wave, _fn


def list_surfaces() -> list[dict[str, Any]]:
    """Operator UI helper — flat list of (slug, title, wave) records."""
    return [
        {"slug": s, "title": t, "wave": w, "pillar": PILLAR}
        for s, t, w in SURFACES
    ]


def call_surface(slug: str, **kwargs: Any) -> dict[str, Any]:
    fn = _BOUND.get(slug)
    if fn is None:
        return {"error": "unknown_surface", "slug": slug, "pillar": PILLAR}
    return fn(**kwargs)
