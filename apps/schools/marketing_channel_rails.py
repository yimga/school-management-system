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


# ---------------------------------------------------------------------------
# Localization
# ---------------------------------------------------------------------------
# Self-contained translation dict (NOT Django gettext/.po) — matches the
# ``MARKETING_COPY_REGISTRY`` approach in ``marketing_media_matrix.py`` so the
# SOT needs no ``makemessages`` step. Keyed by language code, then by the exact
# English source string. English is the canonical source AND the fallback for
# any missing language or string.
#
# Payment-rail labels are proper brand names (M-Pesa / Paystack / Flutterwave /
# MTN MoMo / Orange Money / UPI / Pix / Card / ACH / Bank transfer / SAR rails /
# AED rails). Brand names are NOT translated; only the two generic labels
# ("Card" and "Bank transfer") and the messaging channel "In-app inbox" label +
# every messaging "note" are human-readable and localized.
#
# Priority locales: en (source), fr, es, pt, ar, plus best-effort sw (Swahili),
# ha (Hausa), yo (Yoruba) for the African markets the rails target.

SUPPORTED_LANGS: tuple[str, ...] = ("en", "fr", "es", "pt", "ar", "sw", "ha", "yo")

# Generic (non-brand) payment-rail labels → per-language translation.
_PAYMENT_LABEL_TRANSLATIONS: dict[str, dict[str, str]] = {
    "fr": {"Card": "Carte", "Bank transfer": "Virement bancaire"},
    "es": {"Card": "Tarjeta", "Bank transfer": "Transferencia bancaria"},
    "pt": {"Card": "Cartão", "Bank transfer": "Transferência bancária"},
    "ar": {"Card": "بطاقة", "Bank transfer": "تحويل بنكي"},
    "sw": {"Card": "Kadi", "Bank transfer": "Uhamisho wa benki"},
    "ha": {"Card": "Kati", "Bank transfer": "Canja wurin banki"},
    "yo": {"Card": "Káàdì", "Bank transfer": "Ìfìpamọ́ báńkì"},
}

# Messaging channel labels (only the non-brand "In-app inbox") + notes.
_MESSAGING_TEXT_TRANSLATIONS: dict[str, dict[str, str]] = {
    "fr": {
        "In-app inbox": "Boîte de réception intégrée",
        "Two-way parent threads": "Fils de discussion bidirectionnels avec les parents",
        "Delivery receipts, STOP/opt-out honored": "Accusés de livraison, STOP/désinscription respectés",
        "Receipts, statements, unsubscribe honored": "Reçus, relevés, désabonnement respecté",
        "Threaded messages inside the parent portal": "Messages en fil dans l'espace parent",
    },
    "es": {
        "In-app inbox": "Bandeja dentro de la app",
        "Two-way parent threads": "Hilos bidireccionales con los padres",
        "Delivery receipts, STOP/opt-out honored": "Acuses de entrega, STOP/baja respetados",
        "Receipts, statements, unsubscribe honored": "Recibos, estados de cuenta, baja respetada",
        "Threaded messages inside the parent portal": "Mensajes en hilo dentro del portal de padres",
    },
    "pt": {
        "In-app inbox": "Caixa de entrada no app",
        "Two-way parent threads": "Tópicos bidirecionais com os pais",
        "Delivery receipts, STOP/opt-out honored": "Confirmações de entrega, STOP/descadastro respeitados",
        "Receipts, statements, unsubscribe honored": "Recibos, extratos, cancelamento respeitado",
        "Threaded messages inside the parent portal": "Mensagens em tópicos dentro do portal dos pais",
    },
    "ar": {
        "In-app inbox": "صندوق وارد داخل التطبيق",
        "Two-way parent threads": "محادثات ثنائية الاتجاه مع أولياء الأمور",
        "Delivery receipts, STOP/opt-out honored": "إيصالات التسليم، واحترام STOP/إلغاء الاشتراك",
        "Receipts, statements, unsubscribe honored": "الإيصالات والكشوف واحترام إلغاء الاشتراك",
        "Threaded messages inside the parent portal": "رسائل متسلسلة داخل بوابة ولي الأمر",
    },
    "sw": {
        "In-app inbox": "Kikasha ndani ya programu",
        "Two-way parent threads": "Mazungumzo ya pande mbili na wazazi",
        "Delivery receipts, STOP/opt-out honored": "Risiti za uwasilishaji, STOP/kujiondoa kunaheshimiwa",
        "Receipts, statements, unsubscribe honored": "Risiti, taarifa, kujiondoa kunaheshimiwa",
        "Threaded messages inside the parent portal": "Ujumbe wa mfululizo ndani ya lango la mzazi",
    },
    "ha": {
        "In-app inbox": "Akwatin saƙo cikin manhaja",
        "Two-way parent threads": "Tattaunawar hanya biyu da iyaye",
        "Delivery receipts, STOP/opt-out honored": "Rasidin isarwa, ana girmama STOP/cire suna",
        "Receipts, statements, unsubscribe honored": "Rasidi, bayanai, ana girmama cire rajista",
        "Threaded messages inside the parent portal": "Saƙonni masu jeri cikin tashar iyaye",
    },
    "yo": {
        "In-app inbox": "Àpótí ìfìwéránṣẹ́ nínú áàpù",
        "Two-way parent threads": "Ìjíròrò ọ̀nà méjì pẹ̀lú àwọn òbí",
        "Delivery receipts, STOP/opt-out honored": "Ìwé ẹ̀rí ìfijíṣẹ́, a bọ̀wọ̀ fún STOP/yíyọ̀-kúrò",
        "Receipts, statements, unsubscribe honored": "Àwọn ìwé ẹ̀rí, ìròyìn, a bọ̀wọ̀ fún ìyọ̀ọ̀da-sílẹ̀",
        "Threaded messages inside the parent portal": "Àwọn ìránṣẹ́ onílẹ̀sẹẹsẹ nínú ojú-ọ̀nà òbí",
    },
}


def _normalize_lang(lang: str | None) -> str:
    """Normalize a language code to a supported base code, default ``en``."""
    base = (lang or "en").strip().lower().replace("_", "-").split("-")[0]
    return base if base in SUPPORTED_LANGS else "en"


def _t_payment_label(label: str, lang: str) -> str:
    """Translate a generic (non-brand) payment label, English-fallback."""
    if lang == "en":
        return label
    return _PAYMENT_LABEL_TRANSLATIONS.get(lang, {}).get(label, label)


def _t_messaging(text: str, lang: str) -> str:
    """Translate a messaging label/note, English-fallback on miss."""
    if lang == "en":
        return text
    return _MESSAGING_TEXT_TRANSLATIONS.get(lang, {}).get(text, text)


def _normalize_cc(country_code: str) -> str:
    """Upper-cased, whitespace-trimmed ISO2; tolerant of None."""
    return (country_code or "").strip().upper()


def payment_rails_for_country(country_code: str, lang: str = "en") -> list[dict[str, str]]:
    """Labeled payment rails for a country.

    Wraps/extends ``apm_icons_for_country`` (the existing country catalog) and
    returns ``[{id, label, kind}]`` where ``kind`` is one of
    ``mobile_money`` / ``card`` / ``bank`` / ``wallet``.

    For mobile-money-led markets (KE/NG/GH/UG/TZ/IN/…) the mobile-money rail is
    surfaced FIRST so it draws the eye. Unknown countries fall back to the apm
    catalog default (card + bank).

    ``lang`` is an optional language code (``en``/``fr``/``es``/``pt``/``ar``
    plus best-effort ``sw``/``ha``/``yo``). Brand names (M-Pesa, Paystack, UPI,
    Pix, …) are never translated; only the generic ``Card`` and ``Bank
    transfer`` labels are localized, with English as the fallback.
    """
    cc = _normalize_cc(country_code)
    norm_lang = _normalize_lang(lang)

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

    if norm_lang != "en":
        for rail in rails:
            rail["label"] = _t_payment_label(rail["label"], norm_lang)

    return rails


def messaging_channels_for_country(country_code: str, lang: str = "en") -> list[dict[str, str]]:
    """Labeled messaging channels for a country.

    Returns ``[{id, label, note}]`` for the channels we actually surface:
    WhatsApp, SMS, Email, in-app inbox. For markets where WhatsApp/SMS dominate
    parent comms (NG/KE/GH/IN/ZA/BR/…) WhatsApp + SMS lead; elsewhere Email +
    in-app lead. Notes are honest descriptions of shipped behavior.

    ``lang`` is an optional language code (``en``/``fr``/``es``/``pt``/``ar``
    plus best-effort ``sw``/``ha``/``yo``). Brand labels (WhatsApp, SMS, Email)
    are never translated; only the ``In-app inbox`` label and every ``note`` is
    localized, with English as the fallback.
    """
    cc = _normalize_cc(country_code)
    norm_lang = _normalize_lang(lang)

    whatsapp = {
        "id": "whatsapp",
        "label": "WhatsApp",
        "note": _t_messaging("Two-way parent threads", norm_lang),
    }
    sms = {
        "id": "sms",
        "label": "SMS",
        "note": _t_messaging("Delivery receipts, STOP/opt-out honored", norm_lang),
    }
    email = {
        "id": "email",
        "label": "Email",
        "note": _t_messaging("Receipts, statements, unsubscribe honored", norm_lang),
    }
    inapp = {
        "id": "inapp",
        "label": _t_messaging("In-app inbox", norm_lang),
        "note": _t_messaging("Threaded messages inside the parent portal", norm_lang),
    }

    if cc in _WHATSAPP_FIRST_COUNTRIES:
        return [whatsapp, sms, email, inapp]
    return [email, inapp, whatsapp, sms]
