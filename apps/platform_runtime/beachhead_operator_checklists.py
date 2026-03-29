"""
Tier A beachheads (wedges 1–6): resolved operator checklists for control-plane templates.

No siteconfig singleton coupling — URL names only; callers pass _safe_reverse from super_views_wedge.
"""

from __future__ import annotations

from typing import Any, Callable

# (label, detail, url_name | None, path_doc | None) — url_name reversed on manager; path_doc = tenant API/path hint
_RAW: dict[int, tuple[tuple[str, str, str | None, str | None], ...]] = {
    1: (
        (
            "Create or provision school",
            "Tenant shell + billing; parent/child org for groups.",
            "super:create_school_wizard",
            None,
        ),
        (
            "Setup Studio (guided onboarding)",
            "Region, DNA, packs — low-click go-live path.",
            "siteconfig:guided_onboarding",
            None,
        ),
        (
            "Launch Studio checklist",
            "Pre-flight before cutover.",
            "studio_os:launch",
            None,
        ),
        (
            "Beachhead blueprint packs",
            "IB, UK GCSE/A-Level, US district, UAE MoE+IB seeds.",
            "super:blueprints_catalog",
            None,
        ),
        (
            "App catalog (first-party kits)",
            "Install wedge-tagged marketplace apps per school.",
            "super:app_catalog",
            None,
        ),
        (
            "One SIS, any LMS",
            "SSO → OneRoster → LTI grade passback narrative.",
            "super:one_sis_any_lms",
            None,
        ),
        (
            "Migration cloud",
            "CSV diff, parity, rollback — wedge 1 spine.",
            "super:migration_cloud",
            None,
        ),
        (
            "Learning pack install API",
            "Apply catalog packs programmatically (tenant host).",
            None,
            "POST /api/learning/pack-install/",
        ),
        (
            "Statutory extract JSON",
            "Live headcount-style aggregates (tenant host).",
            None,
            "GET /api/learning/statutory-extract/?stub=…&country=…",
        ),
    ),
    2: (
        (
            "This page: One SIS, any LMS",
            "Certification table + spine steps.",
            "super:one_sis_any_lms",
            None,
        ),
        (
            "API Center",
            "Keys, webhooks, integration governance.",
            "apicenter:dashboard",
            None,
        ),
        (
            "Runtime inspector",
            "Effective config and resolver traces for interop debugging.",
            "super:runtime_inspector",
            None,
        ),
        (
            "District & LMS interop hub (tenant)",
            "OneRoster URLs, token rotate, CSV exports.",
            None,
            "/authentication/backend/district-lms-interop/",
        ),
        (
            "Trust center",
            "Security, audit, compliance overview.",
            "super:trust_center",
            None,
        ),
        (
            "Marketplace compatibility",
            "Scopes and sandbox posture.",
            "super:marketplace_compatibility",
            None,
        ),
    ),
    3: (
        (
            "Curriculum & region packs",
            "GBR + DNA templates; statutory reports entry.",
            "super:curriculum_packs",
            None,
        ),
        (
            "Geography hub",
            "Continent packs; EU includes GBR row for operators.",
            "super:geography",
            None,
        ),
        (
            "Education systems (14–22)",
            "UK/international sector presets.",
            "super:education_systems",
            None,
        ),
        (
            "Trust center",
            "Residency + BCP cards.",
            "super:trust_center",
            None,
        ),
        (
            "Studio output — reports pane",
            "Report and output lineage from Launch/Studio (manager).",
            "studio_os:output",
            None,
        ),
    ),
    4: (
        (
            "District & enterprise hub",
            "Rollups + ERP/government API hints.",
            "super:district_enterprise",
            None,
        ),
        (
            "Group / campuses",
            "Multi-campus governance.",
            "super:group_campuses",
            None,
        ),
        (
            "Schools list",
            "Per-tenant operator drill-down.",
            "super:schools_list",
            None,
        ),
        (
            "Billing console",
            "Subscriptions and usage.",
            "super:billing_dashboard",
            None,
        ),
        (
            "Government aggregates API",
            "Staff/capability gated; schema 1.1+.",
            None,
            "GET /api/government/aggregates/",
        ),
        (
            "API Center",
            "ERP coexistence via webhooks + exports.",
            "apicenter:dashboard",
            None,
        ),
    ),
    5: (
        (
            "Advancement hub",
            "Alumni, campaigns, aid entry points.",
            "super:advancement_hub",
            None,
        ),
        (
            "Phase 2 donors & gifts (manager)",
            "CRM v1: donor + gift capture.",
            "super:advancement_phase2_placeholder",
            None,
        ),
        (
            "Tenant advancement donors",
            "Per-school donor list UI.",
            None,
            "/authentication/backend/advancement/donors/",
        ),
        (
            "Billing console (platform)",
            "Subscriptions, trials, usage — cross-link to tenant finance on school host.",
            "super:billing_dashboard",
            None,
        ),
        (
            "App catalog",
            "Premium communication + engagement packs.",
            "super:app_catalog",
            None,
        ),
    ),
    6: (
        (
            "Learning delivery & institution types",
            "HE type W43 + delivery modes.",
            "super:learning_delivery_packs",
            None,
        ),
        (
            "HE catalog JSON",
            "Automation + Studio partners.",
            "super:learning_institution_catalog_json",
            None,
        ),
        (
            "Plans & addons",
            "HE plan SKUs where enabled.",
            "super:plans_list",
            None,
        ),
        (
            "Install HE wedge packs",
            "degree_audit_he, semester_catalog, graduate_research slugs.",
            None,
            "POST /api/learning/pack-install/  (pack_slug from catalog)",
        ),
        (
            "Curriculum packs",
            "Cross-link to Tier A spine.",
            "super:curriculum_packs",
            None,
        ),
    ),
}


def _bootstrap_registry_wedges(raw: dict[int, tuple[tuple[str, str, str | None, str | None], ...]]) -> None:
    """Fill wedges 7–45 from WEDGE_LINES (skip ids already in Tier A)."""
    from apps.platform_runtime.wedge_line_registry import WEDGE_LINES

    fillers: tuple[tuple[str, str, str | None, str | None], ...] = (
        (
            "Learning pack install API",
            "Apply catalog packs programmatically (tenant host).",
            None,
            "POST /api/learning/pack-install/",
        ),
        (
            "Statutory extract JSON",
            "Live headcount-style aggregates (tenant host).",
            None,
            "GET /api/learning/statutory-extract/?stub=…&country=…",
        ),
        (
            "Runtime truth hub",
            "Platform RuntimeDefaults.payload + slim tenant settings row (read-only).",
            "super:runtime_truth_hub",
            None,
        ),
    )
    for row in WEDGE_LINES:
        wid = int(row["id"])
        if wid in raw:
            continue
        urls = list(row["urls"])
        name = str(row["name"])
        tier = str(row["tier"])
        base_detail = f"Tier {tier} wedge {wid}; registry-backed operator surfaces."
        rows: list[tuple[str, str, str | None, str | None]] = [
            (f"This wedge: {name}", base_detail, urls[0] if urls else None, None),
        ]
        for j, un in enumerate(urls[1:], start=2):
            rows.append(
                (f"Registry surface {j}", "Shipped manager URL for this wedge.", un, None)
            )
        fi = 0
        while len(rows) < 4:
            rows.append(fillers[fi % len(fillers)])
            fi += 1
        raw[wid] = tuple(rows)


_bootstrap_registry_wedges(_RAW)


def build_resolved_beachhead_checklist(
    wedge_id: int,
    safe_reverse: Callable[[str], str | None],
) -> list[dict[str, Any]]:
    """Return checklist rows with `url` set when url_name reverses."""
    raw = _RAW.get(wedge_id)
    if not raw:
        return []
    out: list[dict[str, Any]] = []
    for label, detail, url_name, path_doc in raw:
        url = None
        if url_name:
            url = safe_reverse(url_name)
        out.append(
            {
                "label": label,
                "detail": detail,
                "url": url,
                "path_doc": path_doc,
            }
        )
    return out


def beachhead_wedge_ids() -> tuple[int, ...]:
    return tuple(sorted(_RAW.keys()))
