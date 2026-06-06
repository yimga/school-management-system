"""
Region-aware payment + messaging "rails strip" SOT for public marketing.

In our target markets (Africa, India, MENA, LATAM) the buying trigger is fee
collection via mobile money and parent reach via WhatsApp/SMS — competitors
(Edves, Vidyalaya, Kenyan M-Pesa vendors) LEAD with these. We have the
capability but historically did not surface it. This module builds two small,
honest, region-aware lists the marketing fees + communications pages render
through ``templates/marketing/components/_channel_rails_strip.html``.

Claims are kept honest against ``apps/schools/feature_gap_register.py``:
the real platform features include
``mobile_money_paystack_flutterwave_mtn_orange`` and
``stripe_dynamic_checkout``; messaging (WhatsApp / SMS / email / in-app) lives
in the communication app. Do NOT add a rail here for something we do not ship.

Payment rails build on (and never duplicate) the existing
``marketing_media_matrix.apm_icons_for_country`` country catalog.
"""
from __future__ import annotations

from apps.schools.marketing_media_matrix import apm_icons_for_country

# Mobile-money-led markets: where the mobile-money rail must surface FIRST and
# carry the eye-drawing accent. ISO2 codes.
_MOBILE_MONEY_COUNTRIES: frozenset[str] = frozenset({
    "KE", "NG", "GH", "UG", "TZ", "RW", "ZM", "CI", "CM", "SN", "ML", "BF",
    "IN", "ZA", "ET", "MZ", "MW",
})

# Markets where WhatsApp / SMS dominate parent comms; surface them FIRST.
_WHATSAPP_FIRST_COUNTRIES: frozenset[str] = frozenset({
    "NG", "KE", "GH", "UG", "TZ", "RW", "ZM", "CI", "CM", "SN", "ZA", "ET",
    "MZ", "MW", "IN", "BR", "MX", "ID", "SA", "AE",
})

# Per-country named mobile-money / wallet rails. These name REAL platform
# integrations (Paystack / Flutterwave / MTN MoMo / Orange Money / M-Pesa /
# UPI / Pix). Each entry is {id, label, kind}.
_MOBILE_MONEY_RAILS_BY_COUNTRY: dict[str, list[dict[str, str]]] = {
    "KE": [
        {"id": "mpesa", "label": "M-Pesa", "kind": "mobile_money"},
        {"id": "flutterwave", "label": "Flutterwave", "kind": "mobile_money"},
    ],
    "NG": [
        {"id": "paystack", "label": "Paystack", "kind": "mobile_money"},
        {"id": "flutterwave", "label": "Flutterwave", "kind": "mobile_money"},
    ],
    "GH": [
        {"id": "mtn_momo", "label": "MTN MoMo", "kind": "mobile_money"},
        {"id": "paystack", "label": "Paystack", "kind": "mobile_money"},
    ],
    "UG": [{"id": "mtn_momo", "label": "MTN MoMo", "kind": "mobile_money"}],
    "TZ": [{"id": "mpesa", "label": "M-Pesa", "kind": "mobile_money"}],
    "RW": [{"id": "mtn_momo", "label": "MTN MoMo", "kind": "mobile_money"}],
    "ZM": [{"id": "mtn_momo", "label": "MTN MoMo", "kind": "mobile_money"}],
    "CI": [{"id": "orange_money", "label": "Orange Money", "kind": "mobile_money"}],
    "CM": [{"id": "orange_money", "label": "Orange Money", "kind": "mobile_money"}],
    "SN": [{"id": "orange_money", "label": "Orange Money", "kind": "mobile_money"}],
    "ML": [{"id": "orange_money", "label": "Orange Money", "kind": "mobile_money"}],
    "BF": [{"id": "orange_money", "label": "Orange Money", "kind": "mobile_money"}],
    "ZA": [{"id": "flutterwave", "label": "Flutterwave", "kind": "mobile_money"}],
    "ET": [{"id": "flutterwave", "label": "Flutterwave", "kind": "mobile_money"}],
    "MZ": [{"id": "mpesa", "label": "M-Pesa", "kind": "mobile_money"}],
    "MW": [{"id": "mtn_momo", "label": "MTN MoMo", "kind": "mobile_money"}],
    "IN": [{"id": "upi", "label": "UPI", "kind": "mobile_money"}],
}

# How the existing apm catalog ids map onto rail "kind" buckets.
_APM_KIND_BY_ID: dict[str, str] = {
    "card": "card",
    "ach": "bank",
    "bank": "bank",
    "pix": "mobile_money",
    "upi": "mobile_money",
    "mpesa": "mobile_money",
    "sar": "bank",
    "aed": "bank",
}


def _normalize_cc(country_code: str) -> str:
    """Upper-cased, whitespace-trimmed ISO2; tolerant of None."""
    return (country_code or "").strip().upper()


def payment_rails_for_country(country_code: str) -> list[dict[str, str]]:
    """Labeled payment rails for a country.

    Wraps/extends ``apm_icons_for_country`` (the existing country catalog) and
    returns ``[{id, label, kind}]`` where ``kind`` is one of
    ``mobile_money`` / ``card`` / ``bank`` / ``wallet``.

    For mobile-money-led markets (KE/NG/GH/UG/TZ/IN/…) the mobile-money rail is
    surfaced FIRST so it draws the eye. Unknown countries fall back to the apm
    catalog default (card + bank).
    """
    cc = _normalize_cc(country_code)

    rails: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(rail: dict[str, str]) -> None:
        rid = rail.get("id", "")
        if rid and rid not in seen:
            seen.add(rid)
            rails.append(rail)

    # 1) Mobile-money-led markets: named MoMo / wallet rails first.
    if cc in _MOBILE_MONEY_COUNTRIES:
        for rail in _MOBILE_MONEY_RAILS_BY_COUNTRY.get(cc, []):
            _add(dict(rail))

    # 2) Fold in the existing apm catalog (cards / banks / Pix / SAR rails …),
    #    deriving a kind from the catalog id.
    for icon in apm_icons_for_country(cc):
        iid = icon.get("id", "")
        _add({
            "id": iid,
            "label": icon.get("label", ""),
            "kind": _APM_KIND_BY_ID.get(iid, "card"),
        })

    # 3) Ensure mobile-money markets always lead with a mobile_money rail even
    #    if the named catalog above produced none (defensive).
    if cc in _MOBILE_MONEY_COUNTRIES:
        rails.sort(key=lambda r: 0 if r.get("kind") == "mobile_money" else 1)

    return rails


def messaging_channels_for_country(country_code: str) -> list[dict[str, str]]:
    """Labeled messaging channels for a country.

    Returns ``[{id, label, note}]`` for the channels we actually surface:
    WhatsApp, SMS, Email, in-app inbox. For markets where WhatsApp/SMS dominate
    parent comms (NG/KE/GH/IN/ZA/BR/…) WhatsApp + SMS lead; elsewhere Email +
    in-app lead. Notes are honest descriptions of shipped behavior.
    """
    cc = _normalize_cc(country_code)

    whatsapp = {
        "id": "whatsapp",
        "label": "WhatsApp",
        "note": "Two-way parent threads",
    }
    sms = {
        "id": "sms",
        "label": "SMS",
        "note": "Delivery receipts, STOP/opt-out honored",
    }
    email = {
        "id": "email",
        "label": "Email",
        "note": "Receipts, statements, unsubscribe honored",
    }
    inapp = {
        "id": "inapp",
        "label": "In-app inbox",
        "note": "Threaded messages inside the parent portal",
    }

    if cc in _WHATSAPP_FIRST_COUNTRIES:
        return [whatsapp, sms, email, inapp]
    return [email, inapp, whatsapp, sms]
