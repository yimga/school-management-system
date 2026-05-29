"""v4.00.38 — Institution-type SOT (Wedges 14-22, with deep coverage of 16/17/18).

Two coordinate axes live here:

1. ``INSTITUTION_TYPES`` — the catalog of Tier-C wedges 14-22 with their
   default config knobs (faith traditions list, charter authorizer
   examples, IB programme codes, etc.).

2. ``IB_PROGRAMMES``, ``FAITH_TRADITIONS``, ``CHARTER_AUTHORIZERS`` —
   per-wedge sub-registries that callers can present to the operator as
   pickers.

Where the data is used
----------------------
* ``apps/portal/views_wedge_surfaces.py::institution_types_by_wedge``
  exposes a wedge-scoped picker page at
  ``/portal/super/wedges/institution-types/?wedge=<id>``.
* The same registry feeds the wedge-detail page's checklist live-check
  for wedges 16/17/18 (see ``apps/portal/wedge_checks.py``).
"""
from __future__ import annotations

from typing import Any


# ----- Tier-C institution-type catalog (wedges 14-22) ---------------------


INSTITUTION_TYPES: dict[int, dict[str, Any]] = {
    14: {"code": "public", "label": "Public / state", "default_funding": "state", "needs_authorizer": False},
    15: {"code": "private", "label": "Private / independent", "default_funding": "tuition", "needs_authorizer": False},
    16: {"code": "charter", "label": "Charter / academy", "default_funding": "state-via-authorizer", "needs_authorizer": True},
    17: {"code": "international", "label": "International (IB / Cambridge)", "default_funding": "tuition", "ib_authorized": True},
    18: {"code": "faith-based", "label": "Faith-based", "default_funding": "tuition+endowment", "tradition_required": True},
    19: {"code": "home-school", "label": "Home-school / hybrid", "default_funding": "family"},
    20: {"code": "ministry", "label": "Government / ministry", "default_funding": "state"},
    21: {"code": "ngo", "label": "NGO", "default_funding": "grant"},
    22: {"code": "multi-campus", "label": "Multi-campus / group", "default_funding": "rollup"},
}


# ----- Wedge 16: Charter / academy authorizers -----------------------------


CHARTER_AUTHORIZERS: list[dict[str, str]] = [
    {"code": "us-soe", "label": "US state education department (SEA)", "region": "US"},
    {"code": "us-district", "label": "US local school district authorizer", "region": "US"},
    {"code": "us-university", "label": "US university authorizer", "region": "US"},
    {"code": "us-non-profit", "label": "US non-profit board authorizer", "region": "US"},
    {"code": "uk-academy-trust", "label": "UK Multi-Academy Trust (MAT)", "region": "GB"},
    {"code": "uk-academy-direct", "label": "UK Department for Education direct", "region": "GB"},
    {"code": "se-friskola", "label": "SE Friskola (independent funded)", "region": "SE"},
    {"code": "nl-bijzondere", "label": "NL bijzondere school", "region": "NL"},
]


# ----- Wedge 17: International — IB programme registry --------------------


IB_PROGRAMMES: list[dict[str, str]] = [
    {"code": "pyp", "label": "IB Primary Years Programme (PYP)", "age_band": "3-12"},
    {"code": "myp", "label": "IB Middle Years Programme (MYP)", "age_band": "11-16"},
    {"code": "dp",  "label": "IB Diploma Programme (DP)",       "age_band": "16-19"},
    {"code": "cp",  "label": "IB Career-related Programme (CP)","age_band": "16-19"},
]


CAMBRIDGE_PROGRAMMES: list[dict[str, str]] = [
    {"code": "cam-primary",   "label": "Cambridge Primary",          "age_band": "5-11"},
    {"code": "cam-lower-sec", "label": "Cambridge Lower Secondary",  "age_band": "11-14"},
    {"code": "cam-igcse",     "label": "Cambridge IGCSE",            "age_band": "14-16"},
    {"code": "cam-aice",      "label": "Cambridge AICE / A-Level",   "age_band": "16-19"},
]


# ----- Wedge 18: Faith-based — tradition registry --------------------------


FAITH_TRADITIONS: list[dict[str, str]] = [
    {"code": "catholic", "label": "Catholic"},
    {"code": "anglican", "label": "Anglican / Episcopal"},
    {"code": "protestant-evangelical", "label": "Protestant — Evangelical"},
    {"code": "protestant-mainline", "label": "Protestant — Mainline"},
    {"code": "orthodox-christian", "label": "Orthodox Christian"},
    {"code": "lds", "label": "Latter-day Saints"},
    {"code": "jewish-orthodox", "label": "Jewish — Orthodox"},
    {"code": "jewish-reform", "label": "Jewish — Reform / Conservative"},
    {"code": "islamic-sunni", "label": "Islamic — Sunni"},
    {"code": "islamic-shia", "label": "Islamic — Shia"},
    {"code": "hindu", "label": "Hindu"},
    {"code": "buddhist", "label": "Buddhist"},
    {"code": "sikh", "label": "Sikh"},
    {"code": "baha-i", "label": "Bahá'í"},
    {"code": "interfaith", "label": "Interfaith / Multi-faith"},
]


# ----- accessors ----------------------------------------------------------


def institution_for_wedge(wedge_id: int) -> dict[str, Any] | None:
    return INSTITUTION_TYPES.get(int(wedge_id))


def picker_for_wedge(wedge_id: int) -> dict[str, Any]:
    """Return the sub-registry rows operators pick from for this wedge."""
    wid = int(wedge_id)
    inst = INSTITUTION_TYPES.get(wid) or {}
    if wid == 16:
        return {"institution": inst, "kind": "authorizers", "rows": list(CHARTER_AUTHORIZERS)}
    if wid == 17:
        return {"institution": inst, "kind": "programmes", "rows": list(IB_PROGRAMMES) + list(CAMBRIDGE_PROGRAMMES)}
    if wid == 18:
        return {"institution": inst, "kind": "traditions", "rows": list(FAITH_TRADITIONS)}
    return {"institution": inst, "kind": "type-only", "rows": []}
