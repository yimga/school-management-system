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
}


def get_moe_presets():
    """Return list of preset ids and metadata for UI/API."""
    return [
        {"id": k, **v}
        for k, v in MOE_PRESETS.items()
    ]


def get_moe_preset(preset_id: str):
    """Return one preset by id or None."""
    return MOE_PRESETS.get(preset_id)
