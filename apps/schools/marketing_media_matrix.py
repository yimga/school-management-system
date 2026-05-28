"""
Regional visual asset matrix for public marketing (VISUAL-ENGINE-10X).

Maps ISO country codes to loop variants and APM icon keys. Used by
``marketing_media_context`` and ``{% marketing_asset %}`` template tags.
"""
from __future__ import annotations

from typing import Any

# Markets where marketing emphasizes passive / phone-ban campus tracking copy.
PHONE_BAN_COUNTRIES: frozenset[str] = frozenset({
    "FR",  # common phone restrictions in schools — illustrative routing
})

# Country → sovereign loop bucket (files under static/marketing/video/loops/).
_COUNTRY_LOOP_BUCKET: dict[str, str] = {
    "US": "sovereign_us",
    "CA": "sovereign_us",
    "GB": "sovereign_eu",
    "IE": "sovereign_eu",
    "SA": "sovereign_mena",
    "AE": "sovereign_mena",
    "NG": "sovereign_ssa",
    "KE": "sovereign_ssa",
    "GH": "sovereign_ssa",
    "IN": "sovereign_apac",
    "ID": "sovereign_apac",
    "BR": "sovereign_latam",
    "MX": "sovereign_latam",
}

LOOP_BUCKETS: tuple[str, ...] = (
    "sovereign_default",
    "sovereign_us",
    "sovereign_eu",
    "sovereign_mena",
    "sovereign_ssa",
    "sovereign_apac",
    "sovereign_latam",
)

# Base paths relative to static/ (no leading static/).
VISUAL_ASSET_MATRIX: dict[str, dict[str, str]] = {
    bucket: {
        "sovereign_hero_loop_mp4": f"marketing/video/loops/{bucket}.mp4",
        "sovereign_hero_loop_webm": f"marketing/video/loops/{bucket}.webm",
        "sovereign_hero_poster": f"marketing/img/posters/{bucket}.svg",
        "transit_vector": "images/marketing/platform-offline-sync-console.svg",
    }
    for bucket in LOOP_BUCKETS
}

# Page slug → required manifest keys (Tier S + A).
PAGE_MEDIA_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "home": ("sovereign_hero_loop_mp4", "split_ledger_viz", "transit_viz", "gradebook_viz"),
    "pricing": ("split_ledger_viz", "apm_strip"),
    "platform-fees-payments": ("split_ledger_viz", "apm_strip"),
    "platform-offline-first": ("transit_viz", "sovereign_hero_loop_mp4"),
    "platform-grading-report-cards": ("gradebook_viz",),
    "platform-admissions": ("admissions_flow_mp4",),
    "platform-security": ("transit_vector",),
}

# Marketing sandbox wizard module keys → setup studio step keys (subset).
SANDBOX_MODULE_TO_SETUP_STEP: dict[str, str] = {
    "institution_basics": "institution_basics",
    "plan_choice": "plan_choice",
    "blueprint": "blueprint",
    "branding": "branding",
    "starter_stack": "starter_stack",
    "data_path": "data_path",
    "finance": "starter_stack",
    "offline": "starter_stack",
    "communications": "starter_stack",
}

VALID_SANDBOX_MODULES: frozenset[str] = frozenset(SANDBOX_MODULE_TO_SETUP_STEP.keys())

# platform slug → {% marketing_viz %} key for generic + auto-wired templates
PLATFORM_VIZ_BY_SLUG: dict[str, str] = {
    "platform-admissions": "split_ledger_viz",
    "platform-fees-payments": "split_ledger_viz",
    "platform-offline-first": "transit_viz",
    "platform-grading-report-cards": "gradebook_viz",
    "platform-security": "transit_viz",
    "platform-attendance": "gradebook_viz",
    "platform-analytics": "gradebook_viz",
    "platform-student-information-system": "gradebook_viz",
    "platform-student-portal": "gradebook_viz",
    "platform-teacher-portal": "gradebook_viz",
    "platform-parent-portal": "split_ledger_viz",
    "platform-communications": "split_ledger_viz",
    "platform-workflows": "transit_viz",
    "platform-integrations": "transit_viz",
    "platform-runtime": "transit_viz",
    "platform-control-plane": "transit_viz",
    "platform-education-os": "transit_viz",
    "platform-marketplace": "split_ledger_viz",
    "platform-migration-cloud": "transit_viz",
}


def platform_viz_key_for_slug(slug: str) -> str:
    s = (slug or "").strip().lower()
    if not s.startswith("platform-"):
        return "split_ledger_viz"
    return PLATFORM_VIZ_BY_SLUG.get(s, "split_ledger_viz")


def loop_bucket_for_country(country_code: str) -> str:
    cc = (country_code or "").strip().upper()
    return _COUNTRY_LOOP_BUCKET.get(cc, "sovereign_default")


def assets_for_country(country_code: str) -> dict[str, str]:
    bucket = loop_bucket_for_country(country_code)
    base = dict(VISUAL_ASSET_MATRIX.get(bucket, VISUAL_ASSET_MATRIX["sovereign_default"]))
    base["loop_bucket"] = bucket
    return base


def apm_icons_for_country(country_code: str) -> list[dict[str, str]]:
    """Return illustrative APM labels for Clinical Ledger strip (no live PSP claims)."""
    cc = (country_code or "").strip().upper()
    catalog: dict[str, list[dict[str, str]]] = {
        "US": [
            {"id": "card", "label": "Card"},
            {"id": "ach", "label": "ACH"},
        ],
        "BR": [{"id": "pix", "label": "Pix"}],
        "IN": [{"id": "upi", "label": "UPI"}, {"id": "card", "label": "Card"}],
        "NG": [{"id": "bank", "label": "Bank transfer"}, {"id": "card", "label": "Card"}],
        "KE": [{"id": "mpesa", "label": "M-Pesa"}, {"id": "card", "label": "Card"}],
        "SA": [{"id": "sar", "label": "SAR rails"}, {"id": "card", "label": "Card"}],
        "AE": [{"id": "aed", "label": "AED rails"}, {"id": "card", "label": "Card"}],
    }
    return list(catalog.get(cc, [{"id": "card", "label": "Card"}, {"id": "bank", "label": "Bank transfer"}]))


def marketing_copy_token(country_code: str, token: str, marketing_local: dict[str, Any] | None) -> str:
    """Resolve marketing copy tokens for {% marketing_copy %}."""
    ml = marketing_local or {}
    operational = {
        "US": "Ambient campus tracking — cardstock QR and passive tap counters (illustrative).",
        "SA": "آليات التتبع المحيطي الذكي بدون استخدام هواتف الطلاب",
        "BR": "Rastreamento de campus sem celular no bolso — QR e totens (ilustrativo).",
    }
    mapping = {
        "txt_hero_headline": ml.get("headline_lead") or "Built for schools worldwide",
        "txt_platform_title": "RunMyCampus",
        "txt_governing_body": ml.get("regulatory_line") or "Education authority",
        "txt_operational_claim": operational.get(cc, operational["US"]),
        "txt_student_label": "Students",
        "txt_hero_subheadline": ml.get("hero_subline") or "",
    }
    return str(mapping.get(token, f"[{token}]"))
