"""
Country-local formatting helpers — Wave 4 (v3.62.7).

Address line order, name order (given vs family first), phone dial codes,
and a small set of country-keyed format primitives that the rest of the
platform can lean on when rendering forms / cards / lists in the user's
country format.

Every function here is pure (no DB, no I/O), tolerant of empty input,
never raises. Sweep targets are user-facing — registration, profile,
parent contact card, fee invoice, transcript, certificates, etc.
"""

from __future__ import annotations

from typing import Literal

# ---------------------------------------------------------------------------
# Name order — "given family" (Western) vs "family given" (Eastern + HU).
#
# This determines how to compose a display name from the two fields. Storage
# of `given_name` and `family_name` stays semantic; only render order flips.
# ---------------------------------------------------------------------------

NameOrder = Literal["given-family", "family-given"]

_FAMILY_FIRST_COUNTRIES: frozenset[str] = frozenset({
    # East Asia
    "CN", "JP", "KR", "TW", "HK", "MO", "KP", "VN",
    # Hungarian
    "HU",
    # Other contexts where family-first is the formal convention
    "MN",  # Mongolia
    "KH",  # Cambodia (in formal contexts)
})


def name_order_for(country_code: str | None) -> NameOrder:
    """Return "family-given" for East Asia + Hungary, else "given-family"."""
    return "family-given" if (country_code or "").strip().upper() in _FAMILY_FIRST_COUNTRIES else "given-family"


def compose_full_name(given: str, family: str, country_code: str | None = "") -> str:
    """Compose a display name using the country's culturally-correct ordering.

    Examples:
        compose_full_name("Naomi", "Tanaka", "JP") -> "Tanaka Naomi"
        compose_full_name("Naomi", "Tanaka", "US") -> "Naomi Tanaka"
        compose_full_name("", "Tanaka", "JP")      -> "Tanaka"
        compose_full_name("Naomi", "", "JP")        -> "Naomi"
    """
    g, f = (given or "").strip(), (family or "").strip()
    if not g and not f:
        return ""
    if not g:
        return f
    if not f:
        return g
    if name_order_for(country_code) == "family-given":
        return f"{f} {g}"
    return f"{g} {f}"


# ---------------------------------------------------------------------------
# Address format — per-country field order. Used by profile forms, invoice
# billing-to blocks, parent contact cards, transcript headers, etc.
#
# Stored as an ordered list of field-key strings. Forms render the labels
# in this order; consumers serialize the same order for printable docs.
# ---------------------------------------------------------------------------

# Generic fallback — used for any country not explicitly listed below.
_DEFAULT_ADDRESS_ORDER: tuple[str, ...] = (
    "street",
    "city",
    "region",       # state / province / department / oblast
    "postal_code",
    "country",
)

# Country-specific overrides. Each entry is a tuple of field keys in render
# order. Keys: street, street2, city, region, postal_code, country,
# neighborhood, district, building_number, po_box, prefecture.
ADDRESS_ORDER_BY_COUNTRY: dict[str, tuple[str, ...]] = {
    # US/CA — street, city, state, ZIP, country
    "US": ("street", "street2", "city", "region", "postal_code", "country"),
    "CA": ("street", "street2", "city", "region", "postal_code", "country"),
    # UK — street + street2, city/town, postal_code (no county required), country
    "GB": ("street", "street2", "city", "postal_code", "country"),
    "IE": ("street", "street2", "city", "region", "postal_code", "country"),
    # JP — postal_code first, then prefecture, city, ward, street, building
    "JP": ("postal_code", "region", "city", "district", "street", "street2", "country"),
    # CN — country, province, city, district, street, building
    "CN": ("region", "city", "district", "street", "street2", "postal_code", "country"),
    # KR — similar to CN
    "KR": ("region", "city", "district", "street", "postal_code", "country"),
    # TW — similar to CN, address goes largest -> smallest
    "TW": ("postal_code", "region", "city", "district", "street", "country"),
    # IN — street, area/locality, city, state, PIN code, country
    "IN": ("street", "street2", "district", "city", "region", "postal_code", "country"),
    # BR — street + number, neighborhood, city, state, CEP, country
    "BR": ("street", "neighborhood", "city", "region", "postal_code", "country"),
    # FR — street, city + postal code combined, country
    "FR": ("street", "street2", "postal_code", "city", "country"),
    "BE": ("street", "street2", "postal_code", "city", "country"),
    "DE": ("street", "street2", "postal_code", "city", "country"),
    "AT": ("street", "street2", "postal_code", "city", "country"),
    "CH": ("street", "street2", "postal_code", "city", "country"),
    "NL": ("street", "street2", "postal_code", "city", "country"),
    "IT": ("street", "street2", "postal_code", "city", "region", "country"),
    "ES": ("street", "street2", "postal_code", "city", "region", "country"),
    "PT": ("street", "street2", "postal_code", "city", "country"),
    "SE": ("street", "street2", "postal_code", "city", "country"),
    "NO": ("street", "street2", "postal_code", "city", "country"),
    "DK": ("street", "street2", "postal_code", "city", "country"),
    "FI": ("street", "street2", "postal_code", "city", "country"),
    # NG — street, area, city/state, postal, country
    "NG": ("street", "street2", "district", "city", "region", "postal_code", "country"),
    "KE": ("po_box", "street", "city", "region", "postal_code", "country"),
    "GH": ("po_box", "street", "city", "region", "country"),
    "ZA": ("street", "street2", "city", "region", "postal_code", "country"),
    "EG": ("street", "district", "city", "region", "postal_code", "country"),
    "MA": ("street", "city", "postal_code", "region", "country"),
    # GCC — building number, street, district, city, postal, country
    "AE": ("po_box", "street", "district", "city", "region", "country"),
    "SA": ("building_number", "street", "district", "city", "postal_code", "country"),
    "QA": ("po_box", "street", "district", "city", "country"),
    "KW": ("po_box", "street", "district", "city", "country"),
    # IL — street, city, postal, country
    "IL": ("street", "street2", "city", "postal_code", "country"),
    # AU/NZ — street, suburb, state, postal, country
    "AU": ("street", "street2", "city", "region", "postal_code", "country"),
    "NZ": ("street", "street2", "city", "postal_code", "country"),
}


def address_order_for(country_code: str | None) -> tuple[str, ...]:
    """Return the ordered tuple of address-field keys for `country_code`."""
    cc = (country_code or "").strip().upper()
    return ADDRESS_ORDER_BY_COUNTRY.get(cc, _DEFAULT_ADDRESS_ORDER)


# ---------------------------------------------------------------------------
# Phone — dialing code + national number length. We don't ship full
# libphonenumber here (heavy dependency); just enough to prefix the dial
# code on form labels + the country-specific local format hint.
# ---------------------------------------------------------------------------

DIAL_CODE_BY_COUNTRY: dict[str, str] = {
    "US": "+1", "CA": "+1", "GB": "+44", "IE": "+353",
    "AU": "+61", "NZ": "+64",
    "FR": "+33", "DE": "+49", "ES": "+34", "IT": "+39", "NL": "+31",
    "BE": "+32", "PT": "+351", "CH": "+41", "AT": "+43", "SE": "+46",
    "NO": "+47", "DK": "+45", "FI": "+358", "PL": "+48", "RU": "+7",
    "TR": "+90", "GR": "+30", "CZ": "+420", "RO": "+40",
    "JP": "+81", "KR": "+82", "CN": "+86", "TW": "+886", "HK": "+852",
    "MO": "+853", "MN": "+976",
    "IN": "+91", "PK": "+92", "BD": "+880", "LK": "+94", "NP": "+977",
    "BT": "+975", "MV": "+960", "AF": "+93",
    "ID": "+62", "MY": "+60", "PH": "+63", "SG": "+65", "TH": "+66",
    "VN": "+84", "MM": "+95", "KH": "+855", "LA": "+856", "BN": "+673",
    "TL": "+670",
    "AE": "+971", "SA": "+966", "IL": "+972", "QA": "+974", "KW": "+965",
    "BH": "+973", "OM": "+968", "JO": "+962", "LB": "+961", "IR": "+98",
    "IQ": "+964", "SY": "+963", "YE": "+967", "EG": "+20",
    "NG": "+234", "KE": "+254", "GH": "+233", "ZA": "+27", "ET": "+251",
    "TZ": "+255", "UG": "+256", "DZ": "+213", "MA": "+212", "TN": "+216",
    "ZM": "+260", "ZW": "+263", "MW": "+265", "MZ": "+258", "AO": "+244",
    "BR": "+55", "MX": "+52", "AR": "+54", "CL": "+56", "CO": "+57",
    "PE": "+51", "VE": "+58", "EC": "+593", "BO": "+591", "PY": "+595",
    "UY": "+598", "CR": "+506", "GT": "+502", "HN": "+504", "NI": "+505",
    "PA": "+507", "SV": "+503", "DO": "+1-809", "CU": "+53",
}


def dial_code_for(country_code: str | None) -> str:
    """Return the international dialing prefix (e.g. '+234' for NG)."""
    cc = (country_code or "").strip().upper()
    return DIAL_CODE_BY_COUNTRY.get(cc, "")


# ---------------------------------------------------------------------------
# Postal-code label per country (some countries call it ZIP, PIN, PLZ, CEP,
# Eircode, etc.). Used to label the field correctly in forms.
# ---------------------------------------------------------------------------

POSTAL_CODE_LABEL_BY_COUNTRY: dict[str, str] = {
    "US": "ZIP code",
    "CA": "Postal code",
    "GB": "Postcode",
    "IE": "Eircode",
    "IN": "PIN code",
    "BR": "CEP",
    "DE": "PLZ",
    "AT": "PLZ",
    "CH": "PLZ",
    "FR": "Code postal",
    "ES": "Código postal",
    "IT": "CAP",
    "NL": "Postcode",
    "PT": "Código postal",
    "JP": "郵便番号",
    "CN": "邮政编码",
    "KR": "우편번호",
    "AU": "Postcode",
    "NZ": "Postcode",
    "NG": "Postal code",
    "KE": "Postal code",
    "ZA": "Postal code",
    "EG": "Postal code",
    "AE": "Postal code",
    "SA": "Postal code",
    "IL": "מיקוד",
}


def postal_code_label_for(country_code: str | None) -> str:
    """Return the user-friendly postal-code label (e.g. 'ZIP code' for US)."""
    cc = (country_code or "").strip().upper()
    return POSTAL_CODE_LABEL_BY_COUNTRY.get(cc, "Postal code")


# ---------------------------------------------------------------------------
# Region label per country (some say "State", others "Province", "Region",
# "Department", "Prefecture", "Oblast").
# ---------------------------------------------------------------------------

REGION_LABEL_BY_COUNTRY: dict[str, str] = {
    "US": "State", "AU": "State", "BR": "State", "MX": "State",
    "IN": "State", "NG": "State", "MY": "State", "VE": "State",
    "CA": "Province", "ZA": "Province", "CN": "Province",
    "AR": "Province", "PH": "Province", "TR": "Province",
    "FR": "Région", "ES": "Comunidad", "IT": "Regione", "DE": "Bundesland",
    "AT": "Bundesland", "CH": "Kanton", "BE": "Région",
    "JP": "Prefecture (都道府県)", "KR": "Province (도)",
    "RU": "Oblast", "UA": "Oblast",
    "AE": "Emirate", "SA": "Region", "GB": "County",
    "IE": "County", "KE": "County", "GH": "Region", "ET": "Region",
    "EG": "Governorate", "JO": "Governorate", "LB": "Governorate",
    "IQ": "Governorate",
}


def region_label_for(country_code: str | None) -> str:
    """Return the localized label for the country's first-level subdivision."""
    cc = (country_code or "").strip().upper()
    return REGION_LABEL_BY_COUNTRY.get(cc, "Region")
