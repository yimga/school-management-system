"""
Ministry of Education (MoE) / regulatory report presets for one-click government-compliant export.

Use these keys in "Regulatory Export" menu and APIs to generate country-compliant PDFs
(e.g. WAEC, Bulletin de Notes, Ofsted). Map preset_id to report template family or export logic.
"""

# Preset id -> { name, description, region_hint, template_family or None }
MOE_PRESETS = {
    "waec": {
        "name": "WAEC / WASSCE (West Africa)",
        "description": "West African Examinations Council compliant student/centre return.",
        "region_hint": "NG, GH, GM, SL, LR",
        "template_family": "waec",
    },
    "bulletin_fr": {
        "name": "Bulletin de Notes (Francophone)",
        "description": "French-style term report (Bulletin) with 20-point scale and Moyenne.",
        "region_hint": "FR, SN, CM, CI, BJ",
        "template_family": "francophone",
    },
    "ofsted": {
        "name": "Ofsted-style (UK)",
        "description": "UK regulatory / inspection-style summary export.",
        "region_hint": "GB",
        "template_family": "ofsted",
    },
    "common_core_us": {
        "name": "Common Core / State (US)",
        "description": "US state or Common Core aligned summary export.",
        "region_hint": "US",
        "template_family": "us",
    },
    "cartescolaire": {
        "name": "Carte Scolaire (Cameroon)",
        "description": "Cameroon student registry / Carte Scolaire export.",
        "region_hint": "CM",
        "template_family": "cameroon",
    },
    "asia_generic": {
        "name": "Asia (ministry-style export)",
        "description": "Generic ministry-compliant summary for Asia; extend with country-specific presets (e.g. India CBSE, Singapore) as we go to market.",
        "region_hint": "IN, SG, CN, JP, MY, TH, ID, PH, VN",
        "template_family": None,
    },
    "canada_provincial": {
        "name": "Canada (provincial)",
        "description": "Provincial or territorial aligned summary; extend with province-specific templates (e.g. Ontario, BC) as needed.",
        "region_hint": "CA",
        "template_family": None,
    },
    "latam_es": {
        "name": "Spanish South America (ministry)",
        "description": "Ministry-style export for Spanish-speaking South America (Argentina, Colombia, Chile, Peru, etc.).",
        "region_hint": "AR, CO, CL, PE, EC, BO, PY, UY, VE",
        "template_family": None,
    },
    "mena_generic": {
        "name": "MENA (ministry / regulatory)",
        "description": "Ministry or regulatory summary for Middle East & North Africa; extend with country-specific presets (e.g. UAE, Saudi, Egypt) as we go to market.",
        "region_hint": "AE, SA, EG, JO, LB, KW, BH, QA, OM",
        "template_family": None,
    },
    "india_cbse": {
        "name": "India (CBSE / state boards)",
        "description": "CBSE or state board aligned summary; extend with specific board templates as we go to market.",
        "region_hint": "IN",
        "template_family": None,
    },
}


def get_moe_presets():
    """Return list of preset ids and metadata for UI/API."""
    return [{"id": k, **v} for k, v in MOE_PRESETS.items()]


def get_moe_preset(preset_id: str):
    """Return one preset by id or None."""
    return MOE_PRESETS.get(preset_id)
