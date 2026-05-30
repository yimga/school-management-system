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

PILLAR = "governance_kernel"
SURFACES: tuple[tuple[str, str, int], ...] = (
    ('federated_emis_adapter_state_dept', 'Federated EMIS: state-department adapter', 2),
    ('federated_emis_adapter_ministry', 'Federated EMIS: ministry-of-education adapter', 2),
    ('federated_emis_adapter_district', 'Federated EMIS: district adapter', 2),
    ('federated_emis_adapter_provincial', 'Federated EMIS: provincial adapter', 2),
    ('federated_emis_adapter_council', 'Federated EMIS: education-council adapter', 2),
    ('vc_schema_degree', 'VC: degree credential schema', 2),
    ('vc_schema_transcript', 'VC: transcript credential schema', 2),
    ('vc_schema_attendance', 'VC: attendance credential schema', 2),
    ('vc_schema_badge', 'VC: badge credential schema', 2),
    ('tla_spec_cross_org_dataflow', 'TLA+ spec: CrossOrgDataFlow', 2),
    ('regulator_api_broker_ofgem_uk', 'Regulator broker: UK (CMA)', 2),
    ('regulator_api_broker_cnil_fr', 'Regulator broker: FR (CNIL)', 2),
    ('regulator_api_broker_aepd_es', 'Regulator broker: ES (AEPD)', 2),
    ('regulator_api_broker_apdcat_es', 'Regulator broker: Catalunya (APDCat)', 2),
    ('multimodal_terminology_bsl', 'Multimodal: British Sign Language vocab', 3),
    ('multimodal_terminology_asl', 'Multimodal: American Sign Language vocab', 3),
    ('multimodal_terminology_tagalog', 'Multimodal: spoken Tagalog vocab', 3),
    ('ai_policy_copilot_transcript', 'AI policy: transcript export intent', 3),
    ('ai_policy_copilot_ai_tutor', 'AI policy: AI tutor intent', 3),
    ('ai_policy_copilot_proctoring', 'AI policy: proctoring intent', 3),
    ('ai_policy_copilot_data_export', 'AI policy: data export intent', 3),
    ('cross_org_marketplace_consent_flow', 'Cross-org marketplace consent flow', 3),
    ('regulator_api_broker_ico_uk', 'Regulator broker: UK ICO', 3),
    ('regulator_api_broker_doe_us_state', 'Regulator broker: US DoE state-level', 3),
    ('regulator_api_broker_oai_pe', 'Regulator broker: Peru OAI', 3),
    ('regulator_api_broker_anpd_br', 'Regulator broker: Brazil ANPD', 3),
    ('regulator_api_broker_pdpc_sg', 'Regulator broker: Singapore PDPC', 3),
    ('regulator_api_broker_oaic_au', 'Regulator broker: Australia OAIC', 3),
    ('agentic_self_healing_auto_pr', 'Agentic self-healing: auto-PR opener', 4),
    ('time_traveling_matrix_window_editor', 'Time-traveling matrix: window editor', 4),
    ('time_traveling_matrix_diff_pdf', 'Time-traveling matrix: diff PDF export', 4),
    ('federated_emis_adapter_nce', 'Federated EMIS: NCE adapter', 4),
    ('federated_emis_adapter_oecd', 'Federated EMIS: OECD adapter', 4),
    ('federated_emis_adapter_unesco', 'Federated EMIS: UNESCO UIS adapter', 4),
    ('federated_emis_adapter_worldbank', 'Federated EMIS: World Bank adapter', 4),
    ('vc_schema_health_attestation', 'VC: health attestation schema', 4),
    ('vc_schema_disciplinary_clearance', 'VC: disciplinary clearance schema', 4),
    ('vc_schema_internship_completion', 'VC: internship completion schema', 4),
    ('tla_spec_tenant_isolation_strong', 'TLA+ spec: TenantIsolation v2 (strong)', 4),
    ('regulator_api_broker_ftc_us', 'Regulator broker: US FTC', 4),
    ('regulator_api_broker_office_priv_canada', 'Regulator broker: Canada OPC', 4),
    ('regulator_api_broker_lgpd_br', 'Regulator broker: Brazil LGPD-ANPD v2', 4),
    ('living_competitor_tracker_delta_report', 'Living competitor tracker delta-report auto-emit', 5),
    ('zero_form_bootstrap_closure_verifier', 'Zero-form bootstrap closure verifier', 5),
    ('ai_policy_copilot_grading', 'AI policy: AI grading intent', 5),
    ('ai_policy_copilot_admissions', 'AI policy: admissions intent', 5),
    ('ai_policy_copilot_special_ed', 'AI policy: special ed intent', 5),
    ('ai_policy_copilot_finance', 'AI policy: finance intent', 5),
    ('agentic_self_healing_review_queue', 'Agentic self-healing: review queue', 5),
    ('federated_emis_dp_budget_tracker', 'Federated EMIS: differential privacy budget tracker', 5),
    ('vc_revocation_list', 'VC: revocation list publisher', 5),
    ('vc_status_list_2021', 'VC: StatusList2021 implementation', 5),
    ('regulator_api_broker_dpc_ie', 'Regulator broker: Ireland DPC', 5),
    ('regulator_api_broker_lpdp_my', 'Regulator broker: Malaysia PDPC', 5),
    ('regulator_api_broker_kpkp_id', 'Regulator broker: Indonesia KPKP', 5),
    ('regulator_api_broker_pdpa_th', 'Regulator broker: Thailand PDPA', 5),
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
