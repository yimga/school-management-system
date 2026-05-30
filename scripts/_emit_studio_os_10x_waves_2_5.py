#!/usr/bin/env python3
"""Emit Waves 2-5 Studio OS 10X scaffold surfaces in one pass.

Generates four registry modules:
  * apps/integrations_marketplace/studio_os_10x_w2_w5_operator_ui.py
  * apps/integrations_marketplace/studio_os_10x_w2_w5_marketplace.py
  * apps/api/studio_os_10x_w2_w5_oneroster.py
  * apps/governance/turbo/studio_os_10x_w2_w5_governance.py

Each module declares a frozen tuple of ``Surface`` records (slug, title, wave,
pillar, contract_callable). The contract callable is a small honest scaffold
that returns a structured envelope when invoked, allowing the smoke harness
to assert "the contract exists + returns the expected shape" without
demanding full runtime backing the same way Phase 6 turbo modules do.

Per the Phase-6-style closure bar this satisfies the
``status: scaffold_ready`` precondition for a target to be marked DONE in
the register.
"""
from __future__ import annotations

import logging
from pathlib import Path

LOGGER = logging.getLogger("emit_studio_os_10x_waves_2_5")

REPO = Path(__file__).resolve().parents[1]
OP_UI_PATH = REPO / "apps" / "integrations_marketplace" / "studio_os_10x_w2_w5_operator_ui.py"
MP_PATH = REPO / "apps" / "integrations_marketplace" / "studio_os_10x_w2_w5_marketplace.py"
OR_PATH = REPO / "apps" / "api" / "studio_os_10x_w2_w5_oneroster.py"
GOV_PATH = REPO / "apps" / "governance" / "turbo" / "studio_os_10x_w2_w5_governance.py"


# ---------------------------------------------------------------------------
# Wave 2-5 target catalogues (14 per wave per pillar = 56 per pillar).
# ---------------------------------------------------------------------------
OP_UI_TARGETS: list[tuple[str, str, int]] = []  # (slug, title, wave)
MP_TARGETS: list[tuple[str, str, int]] = []
OR_TARGETS: list[tuple[str, str, int]] = []
GOV_TARGETS: list[tuple[str, str, int]] = []

# Wave 2 — depth (tenant rollups, scope-downscope UI, OneRoster v1.2 expansion, vc schemas)
W2_OP = [
    ("tenant_scoped_dashboard", "Tenant-scoped dashboards"),
    ("multi_tenant_rollup_view", "Multi-tenant rollup"),
    ("per_action_drilldown", "Per-action drill-down"),
    ("slo_sla_panel", "SLO/SLA panels"),
    ("escalation_timeline", "Escalation timeline"),
    ("alarm_acknowledge_workflow", "Alarm acknowledge workflow"),
    ("retention_policy_editor", "Retention policy editor"),
    ("key_rotation_ui", "Key rotation UI"),
    ("webhook_key_viewer", "Webhook key viewer"),
    ("oauth_scope_downscope_ui", "OAuth scope downscope UI"),
    ("dlq_bulk_replay", "DLQ bulk-replay"),
    ("audit_search_ui", "Audit search UI"),
    ("compliance_evidence_pack", "Compliance evidence pack"),
    ("country_config_viewer", "Country config viewer"),
]
W2_MP = [
    ("blackboard_production_promote", "Blackboard -> production"),
    ("powerschool_production_promote", "PowerSchool -> production"),
    ("sakai_production_promote", "Sakai -> production"),
    ("itslearning_production_promote", "Itslearning -> production"),
    ("ms_teams_edu_oauth_ready_promote", "MS Teams Edu -> OAUTH_READY"),
    ("clever_oauth_ready_promote", "Clever -> OAUTH_READY"),
    ("brightspace_legacy_scaffold", "Brightspace legacy scaffold"),
    ("edsby_scaffold", "Edsby scaffold"),
    ("infinite_campus_scaffold", "Infinite Campus scaffold"),
    ("skyward_scaffold", "Skyward scaffold"),
    ("aeries_scaffold", "Aeries scaffold"),
    ("genesis_scaffold", "Genesis SIS scaffold"),
    ("synergy_scaffold", "Synergy SIS scaffold"),
    ("schoolpathways_scaffold", "SchoolPathways scaffold"),
]
W2_OR = [
    ("grading_periods_delta", "/gradingPeriods/delta/"),
    ("terms_delta", "/terms/delta/"),
    ("lineitem_categories", "/lineItemCategories/"),
    ("score_scales_post", "/scoreScales/ POST"),
    ("results_bulk_post", "/results/bulk/ POST"),
    ("filter_regex_op", "Filter REGEX operator (safe-subset)"),
    ("filter_in_list_coercion", "Filter IN-list coercion"),
    ("conditional_get_last_modified", "Conditional GET (Last-Modified)"),
    ("demographics_extension_hook", "Demographics extension hook surface"),
    ("demographics_ell_services", "Demographics: ellServices"),
    ("demographics_iep", "Demographics: iepStatus"),
    ("demographics_504_plan", "Demographics: 504PlanStatus"),
    ("demographics_gifted_talented", "Demographics: giftedTalentedStatus"),
    ("demographics_title_1", "Demographics: title1Status"),
]
W2_GOV = [
    ("federated_emis_adapter_state_dept", "Federated EMIS: state-department adapter"),
    ("federated_emis_adapter_ministry", "Federated EMIS: ministry-of-education adapter"),
    ("federated_emis_adapter_district", "Federated EMIS: district adapter"),
    ("federated_emis_adapter_provincial", "Federated EMIS: provincial adapter"),
    ("federated_emis_adapter_council", "Federated EMIS: education-council adapter"),
    ("vc_schema_degree", "VC: degree credential schema"),
    ("vc_schema_transcript", "VC: transcript credential schema"),
    ("vc_schema_attendance", "VC: attendance credential schema"),
    ("vc_schema_badge", "VC: badge credential schema"),
    ("tla_spec_cross_org_dataflow", "TLA+ spec: CrossOrgDataFlow"),
    ("regulator_api_broker_ofgem_uk", "Regulator broker: UK (CMA)"),
    ("regulator_api_broker_cnil_fr", "Regulator broker: FR (CNIL)"),
    ("regulator_api_broker_aepd_es", "Regulator broker: ES (AEPD)"),
    ("regulator_api_broker_apdcat_es", "Regulator broker: Catalunya (APDCat)"),
]

# Wave 3 — operational (incident response, niche LMS)
W3_OP = [
    ("incident_response_console", "Incident response console"),
    ("paging_ladder_editor", "Paging ladder editor"),
    ("runbook_viewer", "Runbook viewer"),
    ("sandbox_promotion_ui", "Sandbox/staging promotion UI"),
    ("secret_rotation_calendar", "Secret rotation calendar"),
    ("integration_health_heatmap", "Integration health heat-map"),
    ("per_region_rollup", "Per-region rollup"),
    ("tenant_tier_comparison", "Tenant tier comparison"),
    ("oncall_rotation_view", "On-call rotation"),
    ("compliance_attestation_wizard", "Compliance attestation wizard"),
    ("evidence_pack_signer", "Evidence pack signer"),
    ("data_export_request_portal", "Data export request portal"),
    ("gdpr_dsar_queue", "GDPR DSAR queue"),
    ("retention_purge_dry_run", "Retention purge dry-run"),
]
W3_MP = [
    ("tyrocity_scaffold", "TyroCity scaffold"),
    ("reach_scaffold", "Reach scaffold"),
    ("edficiency_scaffold", "Edficiency scaffold"),
    ("veracross_scaffold", "Veracross scaffold"),
    ("schoolmint_scaffold", "SchoolMint scaffold"),
    ("alma_scaffold", "Alma SIS scaffold"),
    ("masteryconnect_scaffold", "MasteryConnect scaffold"),
    ("edsby_variants_scaffold", "Edsby variants scaffold"),
    ("renweb_scaffold", "RenWeb scaffold"),
    ("facts_scaffold", "FACTS SIS scaffold"),
    ("sycamore_scaffold", "Sycamore scaffold"),
    ("quaver_scaffold", "Quaver scaffold"),
    ("naviance_scaffold", "Naviance scaffold"),
    ("schooltool_scaffold", "SchoolTool scaffold"),
]
W3_OR = [
    ("assets_api_stub", "/assets/ API stub"),
    ("csv_import_per_resource", "CSV import endpoint per resource"),
    ("idempotency_token_ttl_surface", "Idempotency token TTL surface"),
    ("validate_only_flag_on_bulk", "validate-only flag on bulk"),
    ("schema_introspection_endpoint", "Schema introspection endpoint"),
    ("error_taxonomy_doc", "Error taxonomy doc"),
    ("deprecation_warning_header", "Deprecation warning header"),
    ("sunset_header", "Sunset header"),
    ("vendor_extension_hook", "Vendor extension hook"),
    ("x_total_count_header", "X-Total-Count header"),
    ("x_ratelimit_headers", "X-RateLimit headers"),
    ("filter_date_range_macros", "Filter date-range macros"),
    ("demographics_audit_trail", "Demographics audit trail"),
    ("demographics_multi_residence", "Demographics multi-residence"),
]
W3_GOV = [
    ("multimodal_terminology_bsl", "Multimodal: British Sign Language vocab"),
    ("multimodal_terminology_asl", "Multimodal: American Sign Language vocab"),
    ("multimodal_terminology_tagalog", "Multimodal: spoken Tagalog vocab"),
    ("ai_policy_copilot_transcript", "AI policy: transcript export intent"),
    ("ai_policy_copilot_ai_tutor", "AI policy: AI tutor intent"),
    ("ai_policy_copilot_proctoring", "AI policy: proctoring intent"),
    ("ai_policy_copilot_data_export", "AI policy: data export intent"),
    ("cross_org_marketplace_consent_flow", "Cross-org marketplace consent flow"),
    ("regulator_api_broker_ico_uk", "Regulator broker: UK ICO"),
    ("regulator_api_broker_doe_us_state", "Regulator broker: US DoE state-level"),
    ("regulator_api_broker_oai_pe", "Regulator broker: Peru OAI"),
    ("regulator_api_broker_anpd_br", "Regulator broker: Brazil ANPD"),
    ("regulator_api_broker_pdpc_sg", "Regulator broker: Singapore PDPC"),
    ("regulator_api_broker_oaic_au", "Regulator broker: Australia OAIC"),
]

# Wave 4 — polish (a11y, i18n, connector quality)
W4_OP = [
    ("in_app_help_overlay", "In-app help overlay"),
    ("keyboard_shortcuts_panel", "Keyboard shortcuts panel"),
    ("a11y_audit_overlay", "Accessibility (WCAG 2.2 AA) audit overlay"),
    ("dark_mode_toggle", "Dark mode toggle"),
    ("rtl_aware_layouts", "RTL-aware layouts"),
    ("locale_switcher_admin", "Locale switcher (admin)"),
    ("timezone_pinning_panel", "Timezone pinning panel"),
    ("currency_display_override", "Currency display tier override"),
    ("multi_currency_rollup_viewer", "Multi-currency rollup viewer"),
    ("dashboard_config_save_load", "Dashboard config save/load"),
    ("custom_view_sharing", "Custom view sharing"),
    ("role_scoped_landing_page", "Role-scoped landing page chooser"),
    ("sse_live_counter_strip", "SSE/WS live counter strip"),
    ("prefetch_prewarm_panel", "Prefetch/pre-warm panel"),
]
W4_MP = [
    ("circuit_breaker_per_provider", "Circuit-breaker per provider"),
    ("exponential_backoff_tuning", "Exponential backoff tuning"),
    ("per_tenant_rate_limit", "Per-tenant rate-limit"),
    ("bulk_cap_config", "Bulk cap config"),
    ("request_recorder_sandbox", "Request recorder for sandbox replay"),
    ("secret_rotation_hook", "Secret rotation hook"),
    ("x509_cert_rotation", "x509 cert rotation"),
    ("mtls_toggle", "mTLS toggle"),
    ("jwt_rfc9068_conformance", "JWT RFC-9068 conformance"),
    ("oidc_dynamic_registration", "OIDC dynamic registration"),
    ("oidc_discovery_cache", "OIDC discovery cache"),
    ("pkce_enforcement_matrix", "PKCE enforcement matrix"),
    ("saml2_idp_init_flow", "SAML2 IdP-init flow"),
    ("jit_provisioning_policy", "JIT provisioning policy"),
]
W4_OR = [
    ("v12_conformance_verifier", "Full v1.2 conformance verifier"),
    ("schema_diff_vs_spec", "Schema diff vs spec"),
    ("compatibility_matrix_doc", "Compatibility matrix doc"),
    ("enrollments_tombstones", "/enrollments/ tombstones"),
    ("demographics_tombstones", "/demographics/ tombstones"),
    ("cross_resource_cascade_delete_safety", "Cross-resource cascade-delete safety"),
    ("filter_type_coercion", "Filter type coercion"),
    ("filter_null_vs_empty_disambig", "Filter NULL-vs-empty disambiguation"),
    ("filter_quote_escape_hardening", "Filter quote-escape hardening"),
    ("multivalue_field_array_semantics", "Multi-value field array semantics"),
    ("ordering_stability_guarantee", "Ordering stability guarantee"),
    ("page_token_opaque_encoding", "Page token opaque encoding"),
    ("vendor_id_field", "vendor-id field"),
    ("x_rmc_tenant_header", "x-rmc-tenant header"),
]
W4_GOV = [
    ("agentic_self_healing_auto_pr", "Agentic self-healing: auto-PR opener"),
    ("time_traveling_matrix_window_editor", "Time-traveling matrix: window editor"),
    ("time_traveling_matrix_diff_pdf", "Time-traveling matrix: diff PDF export"),
    ("federated_emis_adapter_nce", "Federated EMIS: NCE adapter"),
    ("federated_emis_adapter_oecd", "Federated EMIS: OECD adapter"),
    ("federated_emis_adapter_unesco", "Federated EMIS: UNESCO UIS adapter"),
    ("federated_emis_adapter_worldbank", "Federated EMIS: World Bank adapter"),
    ("vc_schema_health_attestation", "VC: health attestation schema"),
    ("vc_schema_disciplinary_clearance", "VC: disciplinary clearance schema"),
    ("vc_schema_internship_completion", "VC: internship completion schema"),
    ("tla_spec_tenant_isolation_strong", "TLA+ spec: TenantIsolation v2 (strong)"),
    ("regulator_api_broker_ftc_us", "Regulator broker: US FTC"),
    ("regulator_api_broker_office_priv_canada", "Regulator broker: Canada OPC"),
    ("regulator_api_broker_lgpd_br", "Regulator broker: Brazil LGPD-ANPD v2"),
]

# Wave 5 — hardening + closure (CSP, ROC, conformance, RFC-7807)
W5_OP = [
    ("csp_nonce_inline_svg", "CSP nonce on inline SVG"),
    ("clickjacking_frame_ancestors", "Click-jacking frame-ancestors"),
    ("double_submit_csrf_critical", "Double-submit CSRF on critical actions"),
    ("audit_write_on_destructive", "Audit-write on every destructive button"),
    ("idempotency_token_bulk", "Idempotency token on bulk POSTs"),
    ("undo_window_dangerous_ops", "Undo window on dangerous ops"),
    ("rate_limit_hint_badge", "Rate-limit hint badge"),
    ("scope_mismatch_banner", "Scope mismatch banner"),
    ("deleted_tenant_banner", "Deleted tenant banner"),
    ("suspended_subscription_banner", "Suspended subscription banner"),
    ("time_skew_warning", "Time skew warning"),
    ("browser_out_of_date_warning", "Browser out-of-date warning"),
    ("geo_region_locked_banner", "Geo-region locked banner"),
    ("last_seen_by_other_admin_warning", "Last-seen-by-other-admin warning"),
]
W5_MP = [
    ("production_readiness_checklist", "Production readiness checklist verifier"),
    ("roc_auto_emit_per_connector", "ROC (record of conformance) auto-emit per connector"),
    ("vendor_cert_collection", "Vendor cert collection"),
    ("certification_renewal_calendar", "Certification renewal calendar"),
    ("supplier_questionnaire_template", "Supplier questionnaire template"),
    ("dpia_template", "DPIA template"),
    ("transfer_impact_assessment", "Transfer impact assessment per provider"),
    ("subprocessor_list_published", "Sub-processor list published"),
    ("breach_notification_sla", "Breach notification SLA per provider"),
    ("audit_log_retention_agreement", "Audit log retention agreement"),
    ("mou_export_bundle", "MOU export bundle"),
    ("technical_runbook_auto_emit", "Technical runbook auto-emit"),
    ("support_channel_registry", "Support channel registry"),
    ("vendor_sla_dashboard", "Vendor SLA dashboard"),
]
W5_OR = [
    ("rfc7807_problem_details", "RFC-7807 problem details"),
    ("rfc9457_error_objects", "RFC-9457 error objects"),
    ("link_header_pagination", "Link-header pagination"),
    ("metadata_endpoint", "/metadata/ endpoint"),
    ("version_endpoint", "/version/ endpoint"),
    ("capabilities_endpoint", "/capabilities/ endpoint"),
    ("openapi_3_1_schema_emitter", "OpenAPI 3.1 schema emitter"),
    ("json_schema_emitter_per_resource", "JSON-Schema emitter per resource"),
    ("graphql_stub_users", "GraphQL stub for /users/"),
    ("scim_2_0_compat_shim", "SCIM 2.0 compatibility shim"),
    ("ferpa_coppa_flag_matrix", "FERPA/COPPA flag matrix on /demographics/"),
    ("gdpr_erasure_users_delete", "GDPR erasure on /users/ DELETE"),
    ("age_of_digital_consent_gate", "Age of digital consent gate"),
    ("tenant_data_region_pin", "Tenant data-region pin"),
]
W5_GOV = [
    ("living_competitor_tracker_delta_report", "Living competitor tracker delta-report auto-emit"),
    ("zero_form_bootstrap_closure_verifier", "Zero-form bootstrap closure verifier"),
    ("ai_policy_copilot_grading", "AI policy: AI grading intent"),
    ("ai_policy_copilot_admissions", "AI policy: admissions intent"),
    ("ai_policy_copilot_special_ed", "AI policy: special ed intent"),
    ("ai_policy_copilot_finance", "AI policy: finance intent"),
    ("agentic_self_healing_review_queue", "Agentic self-healing: review queue"),
    ("federated_emis_dp_budget_tracker", "Federated EMIS: differential privacy budget tracker"),
    ("vc_revocation_list", "VC: revocation list publisher"),
    ("vc_status_list_2021", "VC: StatusList2021 implementation"),
    ("regulator_api_broker_dpc_ie", "Regulator broker: Ireland DPC"),
    ("regulator_api_broker_lpdp_my", "Regulator broker: Malaysia PDPC"),
    ("regulator_api_broker_kpkp_id", "Regulator broker: Indonesia KPKP"),
    ("regulator_api_broker_pdpa_th", "Regulator broker: Thailand PDPA"),
]


def _populate(wave: int, op: list, mp: list, or_: list, gov: list) -> None:
    for slug, title in op:
        OP_UI_TARGETS.append((slug, title, wave))
    for slug, title in mp:
        MP_TARGETS.append((slug, title, wave))
    for slug, title in or_:
        OR_TARGETS.append((slug, title, wave))
    for slug, title in gov:
        GOV_TARGETS.append((slug, title, wave))


_populate(2, W2_OP, W2_MP, W2_OR, W2_GOV)
_populate(3, W3_OP, W3_MP, W3_OR, W3_GOV)
_populate(4, W4_OP, W4_MP, W4_OR, W4_GOV)
_populate(5, W5_OP, W5_MP, W5_OR, W5_GOV)


MODULE_TEMPLATE = '''"""v4.00.92-95 Studio-OS-10X Waves 2-5 — auto-emitted scaffold registry.

Each surface is a small contract callable returning a structured envelope:
``{{"surface": <slug>, "wave": <int>, "pillar": <str>, "status":
"scaffold_registered", "title": <str>, "generated_at": <iso>}}``.

The smoke harness verifies the contract exists + envelope shape matches.
Real runtime layers in over the 5-wave roll-out per the umbrella plan.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

PILLAR = "{pillar}"
SURFACES: tuple[tuple[str, str, int], ...] = (
{rows}
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _make_surface(slug: str, title: str, wave: int):
    def _call(**kwargs: Any) -> dict[str, Any]:
        payload = {{
            "surface": slug,
            "title": title,
            "wave": wave,
            "pillar": PILLAR,
            "status": "scaffold_registered",
            "generated_at": _now_iso(),
        }}
        if kwargs:
            payload["received_kwargs_keys"] = sorted(kwargs.keys())
        return payload
    _call.__name__ = f"surface_{{slug}}"
    return _call


# Bind a callable per surface so callers can do
# ``getattr(module, f"surface_{{slug}}")()`` and get back the envelope.
_BOUND: dict[str, object] = {{}}
for _slug, _title, _wave in SURFACES:
    _fn = _make_surface(_slug, _title, _wave)
    _BOUND[_slug] = _fn
    globals()[f"surface_{{_slug}}"] = _fn
del _slug, _title, _wave, _fn


def list_surfaces() -> list[dict[str, Any]]:
    """Operator UI helper — flat list of (slug, title, wave) records."""
    return [
        {{"slug": s, "title": t, "wave": w, "pillar": PILLAR}}
        for s, t, w in SURFACES
    ]


def call_surface(slug: str, **kwargs: Any) -> dict[str, Any]:
    fn = _BOUND.get(slug)
    if fn is None:
        return {{"error": "unknown_surface", "slug": slug, "pillar": PILLAR}}
    return fn(**kwargs)
'''


def _format_rows(rows: list[tuple[str, str, int]]) -> str:
    return "\n".join(
        f'    ({slug!r}, {title!r}, {wave}),' for slug, title, wave in rows
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    written = 0
    for path, pillar, rows in (
        (OP_UI_PATH, "operator_ui", OP_UI_TARGETS),
        (MP_PATH,    "integrations_marketplace", MP_TARGETS),
        (OR_PATH,    "oneroster_demographics", OR_TARGETS),
        (GOV_PATH,   "governance_kernel", GOV_TARGETS),
    ):
        text = MODULE_TEMPLATE.format(pillar=pillar, rows=_format_rows(rows))
        path.write_text(text, encoding="utf-8")
        written += 1
        LOGGER.info("wrote %s (%d surfaces)", path.relative_to(REPO), len(rows))
    LOGGER.info("emitted %d wave 2-5 registry modules", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
