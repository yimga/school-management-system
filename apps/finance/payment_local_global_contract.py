"""
Local-global payment profile contract (SFDP Phase 3 — batches 1452, 1459–1466).

Enriches regional_payment_profiles.json rows with currency display, locale hints,
risk tier, local rail vocabulary, and honest small-market fallback posture.
"""

from __future__ import annotations

from typing import Any

from apps.finance.payment_rail_taxonomy import (
    RAIL_BANK,
    RAIL_CARD,
    RAIL_CASH,
    RAIL_INSTANT_BANK,
    RAIL_MANUAL_PROOF,
    RAIL_MPESA,
    RAIL_MTN_MOMO,
    RAIL_ORANGE_MOMO,
    RAIL_PIX,
    RAIL_UPI,
    RAIL_VOUCHER,
    RAIL_WALLET,
    canonical_classes_for_profile,
)
from apps.finance.payment_risk_tier import default_risk_tier_for_country

PHASE3_REQUIRED_FIELDS: tuple[str, ...] = (
    "country_code",
    "label",
    "currency",
    "currency_display",
    "minor_units",
    "primary_rail",
    "backup_rail",
    "manual_fallback",
    "offline_receipt_allowed",
    "provider_setup_status",
    "operator_ready_label",
    "operator_setup_steps",
    "tenant_setup_steps",
    "locale_hints",
    "risk_tier",
    "local_rail_vocabulary",
    "canonical_rail_classes",
    "checkout_rail_order",
    "settlement_currency",
    "small_market_fallback",
    "receipt_locale_key",
)

EUROZONE_ISO2: frozenset[str] = frozenset(
    {
        "AT",
        "BE",
        "CY",
        "DE",
        "EE",
        "ES",
        "FI",
        "FR",
        "GR",
        "HR",
        "IE",
        "IT",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "PT",
        "SI",
        "SK",
    }
)

CFA_XAF_ISO2: frozenset[str] = frozenset({"CM", "CF", "TD", "CG", "GQ", "GA"})
CFA_XOF_ISO2: frozenset[str] = frozenset({"BJ", "BF", "CI", "GW", "ML", "NE", "SN", "TG"})

CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "NGN": "₦",
    "GHS": "₵",
    "KES": "KSh",
    "XAF": "FCFA",
    "XOF": "CFA",
    "BRL": "R$",
    "INR": "₹",
    "AED": "د.إ",
    "SAR": "﷼",
    "CAD": "CA$",
    "AUD": "A$",
    "IDR": "Rp",
    "PHP": "₱",
    "THB": "฿",
    "VND": "₫",
    "EGP": "E£",
    "MAD": "DH",
    "MXN": "MX$",
    "PKR": "₨",
    "BDT": "৳",
    "LKR": "Rs",
}

CURRENCY_MINOR_UNITS: dict[str, int] = {
    "XAF": 0,
    "XOF": 0,
    "JPY": 0,
    "KRW": 0,
    "VND": 0,
}

ISO2_CURRENCY_OVERRIDES: dict[str, str] = {
    "US": "USD",
    "GB": "GBP",
    "NG": "NGN",
    "GH": "GHS",
    "CM": "XAF",
    "KE": "KES",
    "BR": "BRL",
    "IN": "INR",
    "AE": "AED",
    "SA": "SAR",
    "FR": "EUR",
    "DE": "EUR",
    "CA": "CAD",
    "AU": "AUD",
    "MX": "MXN",
    "ID": "IDR",
    "PH": "PHP",
    "TH": "THB",
    "VN": "VND",
    "EG": "EGP",
    "MA": "MAD",
    "PK": "PKR",
    "BD": "BDT",
    "LK": "LKR",
    "CO": "COP",
    "CL": "CLP",
    "PE": "PEN",
    "ZA": "ZAR",
    "TZ": "TZS",
    "UG": "UGX",
    "RW": "RWF",
    "SN": "XOF",
    "CI": "XOF",
}

REGION_DEPTH_PACKS: dict[str, dict[str, Any]] = {
    "BR": {
        "label": "Brazil",
        "currency": "BRL",
        "currency_display": "Real brasileiro (BRL)",
        "primary_rails": [RAIL_PIX, RAIL_CARD, RAIL_BANK],
        "backup_rails": [RAIL_CASH, RAIL_MANUAL_PROOF],
        "local_rail_vocabulary": {
            RAIL_PIX: "Pix",
            RAIL_CARD: "Cartão",
            RAIL_BANK: "Transferência bancária",
            RAIL_CASH: "Dinheiro",
        },
        "locale_hints": {"language": "pt", "direction": "ltr", "parent_term": "responsável"},
        "receipt_locale_key": "finance.receipt.br",
        "notes": "Pix is primary for tuition; cards via Stripe/dLocal when entitled.",
    },
    "MX": {
        "label": "Mexico",
        "currency": "MXN",
        "currency_display": "Peso mexicano (MXN)",
        "primary_rails": [RAIL_INSTANT_BANK, RAIL_CARD, RAIL_VOUCHER],
        "backup_rails": [RAIL_CASH, RAIL_MANUAL_PROOF],
        "local_rail_vocabulary": {
            RAIL_INSTANT_BANK: "SPEI",
            RAIL_VOUCHER: "OXXO / voucher",
            RAIL_CARD: "Tarjeta",
        },
        "locale_hints": {"language": "es", "direction": "ltr", "parent_term": "tutor"},
        "receipt_locale_key": "finance.receipt.mx",
    },
    "IN": {
        "label": "India",
        "currency": "INR",
        "currency_display": "Indian rupee (INR)",
        "primary_rails": [RAIL_UPI, RAIL_BANK, RAIL_CARD],
        "backup_rails": [RAIL_CASH, RAIL_MANUAL_PROOF],
        "local_rail_vocabulary": {
            RAIL_UPI: "UPI",
            RAIL_BANK: "NEFT / IMPS",
            RAIL_CARD: "Card",
        },
        "locale_hints": {"language": "en", "direction": "ltr", "parent_term": "guardian"},
        "receipt_locale_key": "finance.receipt.in",
    },
    "ID": {
        "label": "Indonesia",
        "currency": "IDR",
        "currency_display": "Rupiah (IDR)",
        "primary_rails": [RAIL_WALLET, RAIL_BANK, RAIL_CARD],
        "backup_rails": [RAIL_CASH, RAIL_MANUAL_PROOF],
        "local_rail_vocabulary": {RAIL_WALLET: "QRIS / e-wallet", RAIL_BANK: "Virtual account"},
        "locale_hints": {"language": "id", "direction": "ltr", "parent_term": "wali"},
        "receipt_locale_key": "finance.receipt.id",
    },
    "AE": {
        "label": "United Arab Emirates",
        "currency": "AED",
        "currency_display": "UAE dirham (AED)",
        "primary_rails": [RAIL_CARD, RAIL_BANK],
        "backup_rails": [RAIL_CASH, RAIL_MANUAL_PROOF],
        "local_rail_vocabulary": {RAIL_CARD: "Card", RAIL_BANK: "Bank transfer"},
        "locale_hints": {"language": "ar", "direction": "rtl", "parent_term": "ولي الأمر"},
        "receipt_locale_key": "finance.receipt.ae",
    },
    "FR": {
        "label": "France",
        "currency": "EUR",
        "currency_display": "Euro (EUR)",
        "primary_rails": [RAIL_BANK, RAIL_CARD],
        "backup_rails": [RAIL_CASH, RAIL_MANUAL_PROOF],
        "local_rail_vocabulary": {RAIL_BANK: "Virement SEPA", RAIL_CARD: "Carte bancaire"},
        "locale_hints": {"language": "fr", "direction": "ltr", "parent_term": "responsable légal"},
        "receipt_locale_key": "finance.receipt.fr",
        "tax_wording_key": "finance.vat.placeholder.fr",
    },
    "CA": {
        "label": "Canada",
        "currency": "CAD",
        "currency_display": "Canadian dollar (CAD)",
        "primary_rails": [RAIL_CARD, RAIL_INSTANT_BANK],
        "backup_rails": [RAIL_CASH, RAIL_MANUAL_PROOF],
        "local_rail_vocabulary": {
            RAIL_INSTANT_BANK: "Interac e-Transfer",
            RAIL_CARD: "Card",
        },
        "locale_hints": {"language": "en", "direction": "ltr", "parent_term": "guardian"},
        "receipt_locale_key": "finance.receipt.ca",
    },
}


def _country_label(iso2: str) -> str:
    try:
        import pycountry

        c = pycountry.countries.get(alpha_2=iso2)
        if c and c.name:
            return str(c.name)
    except Exception:
        pass
    return iso2


def resolve_currency(iso2: str, row: dict[str, Any]) -> str:
    existing = str(row.get("currency") or "").strip().upper()
    stub_marker = "Phase 2 stub" in str(row.get("notes") or "")
    if existing and existing != "USD" and not stub_marker:
        return existing
    if iso2 in ISO2_CURRENCY_OVERRIDES:
        return ISO2_CURRENCY_OVERRIDES[iso2]
    if iso2 in EUROZONE_ISO2:
        return "EUR"
    if iso2 in CFA_XAF_ISO2:
        return "XAF"
    if iso2 in CFA_XOF_ISO2:
        return "XOF"
    if existing:
        return existing
    return "USD"


def _minor_units(currency: str) -> int:
    return CURRENCY_MINOR_UNITS.get(currency.upper(), 2)


def _currency_display(currency: str, label: str) -> str:
    sym = CURRENCY_SYMBOLS.get(currency.upper(), currency.upper())
    return f"{label} ({currency.upper()}) · {sym}"


def _default_rail_vocabulary(rails: list[str]) -> dict[str, str]:
    defaults = {
        RAIL_BANK: "Bank transfer",
        RAIL_CARD: "Card",
        RAIL_CASH: "Cash",
        RAIL_MTN_MOMO: "Mobile money",
        RAIL_ORANGE_MOMO: "Orange Money",
        RAIL_MPESA: "M-Pesa",
        RAIL_WALLET: "Wallet",
        RAIL_PIX: "Pix",
        RAIL_UPI: "UPI",
        RAIL_INSTANT_BANK: "Instant bank transfer",
        RAIL_VOUCHER: "Voucher / cash-in",
        RAIL_MANUAL_PROOF: "Proof upload",
    }
    return {r: defaults.get(r, r.replace("_", " ").title()) for r in rails if r}


def apply_phase3_enrichment(iso2: str, row: dict[str, Any]) -> dict[str, Any]:
    """Return enriched copy; does not mutate input."""
    out = dict(row)
    code = str(iso2).strip().upper()[:2]
    out["country_code"] = code

    pack = REGION_DEPTH_PACKS.get(code, {})
    for key, val in pack.items():
        out[key] = val

    if out.get("label") in (None, "", code):
        out["label"] = _country_label(code)

    currency = resolve_currency(code, out)
    out["currency"] = currency
    out["settlement_currency"] = str(out.get("settlement_currency") or currency)
    out["currency_display"] = str(
        out.get("currency_display") or _currency_display(currency, out["label"])
    )
    out["minor_units"] = int(out.get("minor_units") if out.get("minor_units") is not None else _minor_units(currency))

    primaries = list(out.get("primary_rails") or [])
    backups = list(out.get("backup_rails") or [])
    if not primaries:
        primaries = [str(out.get("primary_rail") or RAIL_BANK)]
    if not backups:
        backups = [str(out.get("backup_rail") or RAIL_CASH)]
    out["primary_rails"] = primaries
    out["backup_rails"] = backups
    out["primary_rail"] = str(out.get("primary_rail") or primaries[0])
    out["backup_rail"] = str(out.get("backup_rail") or (backups[0] if backups else ""))

    all_rails = primaries + backups
    out["local_rail_vocabulary"] = {
        ** _default_rail_vocabulary(all_rails),
        **(out.get("local_rail_vocabulary") or {}),
    }
    out["checkout_rail_order"] = list(out.get("checkout_rail_order") or primaries + backups)
    out["canonical_rail_classes"] = list(out.get("canonical_rail_classes") or canonical_classes_for_profile(out))

    out["risk_tier"] = str(out.get("risk_tier") or default_risk_tier_for_country(code))
    out["locale_hints"] = dict(
        out.get("locale_hints")
        or {"language": "en", "direction": "ltr", "parent_term": "guardian"}
    )
    out["receipt_locale_key"] = str(out.get("receipt_locale_key") or f"finance.receipt.{code.lower()}")

    stub = "Phase 2 stub" in str(out.get("notes") or "")
    out["small_market_fallback"] = bool(
        out.get("small_market_fallback")
        if out.get("small_market_fallback") is not None
        else stub or out.get("provider_setup_status") == "external_required"
    )
    if out["small_market_fallback"] and stub:
        out["operator_ready_label"] = str(
            out.get("operator_ready_label")
            or "Honest fallback — bank transfer, cash desk, or proof upload until PSP connects."
        )
        out["notes"] = str(
            out.get("notes")
            or "No direct PSP in catalog yet; cash and manual proof remain available with staff reconciliation."
        )

    return out


def validate_profile_contract(row: dict[str, Any] | None, *, iso2: str = "") -> list[str]:
    if not row:
        return [f"{iso2 or '?'}: missing profile"]
    findings: list[str] = []
    for field in PHASE3_REQUIRED_FIELDS:
        val = row.get(field)
        if val in (None, "", []):
            findings.append(f"{iso2}: missing {field}")
    classes = row.get("canonical_rail_classes") or []
    if not classes:
        findings.append(f"{iso2}: empty canonical_rail_classes")
    if str(row.get("label") or "").strip() == iso2 and not row.get("small_market_fallback"):
        findings.append(f"{iso2}: generic-only label")
    return findings


def validate_all_profiles(profiles: dict[str, dict[str, Any]]) -> list[str]:
    findings: list[str] = []
    for iso2, raw in sorted(profiles.items()):
        enriched = apply_phase3_enrichment(iso2, raw if isinstance(raw, dict) else {})
        findings.extend(validate_profile_contract(enriched, iso2=iso2))
    return findings
