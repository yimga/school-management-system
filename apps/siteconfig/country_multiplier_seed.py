"""Platform catalog seed for ``CountryMultiplier`` PPP bands.

Source: World Bank PPP conversion factor (GDP), indexed to US=1.0, rounded for
SaaS price bands (2024 baseline). Tax rates are indicative VAT/GST defaults;
operators may override per country in the control plane.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, TypedDict

from apps.siteconfig.global_catalog import GlobalGeoCatalog

# Provenance string stored in migration/command logs (not a DB column).
PPP_SEED_SOURCE = (
    "World Bank PPP conversion factor (GDP), US=1.0 indexed, 2024 baseline bands"
)


class CountryMultiplierSeedRow(TypedDict):
    country_code: str
    zone: str
    multiplier: Decimal
    tax_rate: Decimal
    tax_code: str
    name: str


# Curated Tier-1 / Africa / South Asia focus markets (+ US/GB/EU anchors).
COUNTRY_MULTIPLIER_SEED_ROWS: tuple[CountryMultiplierSeedRow, ...] = (
    {"country_code": "US", "zone": "A", "multiplier": Decimal("1.0000"), "tax_rate": Decimal("0.0000"), "tax_code": "", "name": "United States"},
    {"country_code": "CA", "zone": "A", "multiplier": Decimal("0.9500"), "tax_rate": Decimal("0.0500"), "tax_code": "GST/HST", "name": "Canada"},
    {"country_code": "GB", "zone": "A", "multiplier": Decimal("0.9500"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "United Kingdom"},
    {"country_code": "DE", "zone": "A", "multiplier": Decimal("0.9200"), "tax_rate": Decimal("0.1900"), "tax_code": "VAT", "name": "Germany"},
    {"country_code": "FR", "zone": "A", "multiplier": Decimal("0.9000"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "France"},
    {"country_code": "AU", "zone": "A", "multiplier": Decimal("0.9000"), "tax_rate": Decimal("0.1000"), "tax_code": "GST", "name": "Australia"},
    {"country_code": "SG", "zone": "A", "multiplier": Decimal("0.9500"), "tax_rate": Decimal("0.0900"), "tax_code": "GST", "name": "Singapore"},
    {"country_code": "AE", "zone": "B", "multiplier": Decimal("0.8500"), "tax_rate": Decimal("0.0500"), "tax_code": "VAT", "name": "United Arab Emirates"},
    {"country_code": "KE", "zone": "B", "multiplier": Decimal("0.7500"), "tax_rate": Decimal("0.1600"), "tax_code": "VAT", "name": "Kenya"},
    {"country_code": "ZA", "zone": "B", "multiplier": Decimal("0.4500"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "South Africa"},
    {"country_code": "BR", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.1700"), "tax_code": "ICMS", "name": "Brazil"},
    {"country_code": "MX", "zone": "B", "multiplier": Decimal("0.4500"), "tax_rate": Decimal("0.1600"), "tax_code": "IVA", "name": "Mexico"},
    {"country_code": "MA", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "Morocco"},
    {"country_code": "CM", "zone": "C", "multiplier": Decimal("0.3200"), "tax_rate": Decimal("0.1925"), "tax_code": "VAT", "name": "Cameroon"},
    {"country_code": "NG", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.0750"), "tax_code": "VAT", "name": "Nigeria"},
    {"country_code": "GH", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Ghana"},
    {"country_code": "UG", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Uganda"},
    {"country_code": "TZ", "zone": "C", "multiplier": Decimal("0.2800"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Tanzania"},
    {"country_code": "RW", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Rwanda"},
    {"country_code": "SN", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Senegal"},
    {"country_code": "CI", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Côte d'Ivoire"},
    {"country_code": "IN", "zone": "C", "multiplier": Decimal("0.2800"), "tax_rate": Decimal("0.1800"), "tax_code": "GST", "name": "India"},
    {"country_code": "PK", "zone": "C", "multiplier": Decimal("0.2500"), "tax_rate": Decimal("0.1700"), "tax_code": "GST", "name": "Pakistan"},
    {"country_code": "BD", "zone": "C", "multiplier": Decimal("0.2800"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Bangladesh"},
    {"country_code": "EG", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1400"), "tax_code": "VAT", "name": "Egypt"},
    {"country_code": "ET", "zone": "C", "multiplier": Decimal("0.2500"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Ethiopia"},
    # Wave 20 — curated depth (Asia / LatAm / EU / MENA anchors; World Bank PPP bands).
    {"country_code": "JP", "zone": "A", "multiplier": Decimal("0.8800"), "tax_rate": Decimal("0.1000"), "tax_code": "CT", "name": "Japan"},
    {"country_code": "KR", "zone": "A", "multiplier": Decimal("0.8500"), "tax_rate": Decimal("0.1000"), "tax_code": "VAT", "name": "South Korea"},
    {"country_code": "CN", "zone": "B", "multiplier": Decimal("0.5500"), "tax_rate": Decimal("0.1300"), "tax_code": "VAT", "name": "China"},
    {"country_code": "HK", "zone": "A", "multiplier": Decimal("0.9200"), "tax_rate": Decimal("0.0000"), "tax_code": "", "name": "Hong Kong"},
    {"country_code": "TW", "zone": "A", "multiplier": Decimal("0.7800"), "tax_rate": Decimal("0.0500"), "tax_code": "VAT", "name": "Taiwan"},
    {"country_code": "ID", "zone": "C", "multiplier": Decimal("0.3200"), "tax_rate": Decimal("0.1100"), "tax_code": "VAT", "name": "Indonesia"},
    {"country_code": "PH", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1200"), "tax_code": "VAT", "name": "Philippines"},
    {"country_code": "VN", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1000"), "tax_code": "VAT", "name": "Vietnam"},
    {"country_code": "TH", "zone": "B", "multiplier": Decimal("0.4200"), "tax_rate": Decimal("0.0700"), "tax_code": "VAT", "name": "Thailand"},
    {"country_code": "MY", "zone": "B", "multiplier": Decimal("0.4500"), "tax_rate": Decimal("0.0600"), "tax_code": "SST", "name": "Malaysia"},
    {"country_code": "CL", "zone": "B", "multiplier": Decimal("0.5000"), "tax_rate": Decimal("0.1900"), "tax_code": "IVA", "name": "Chile"},
    {"country_code": "CO", "zone": "B", "multiplier": Decimal("0.3800"), "tax_rate": Decimal("0.1900"), "tax_code": "IVA", "name": "Colombia"},
    {"country_code": "AR", "zone": "B", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.2100"), "tax_code": "IVA", "name": "Argentina"},
    {"country_code": "PE", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.1800"), "tax_code": "IGV", "name": "Peru"},
    {"country_code": "TR", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.2000"), "tax_code": "KDV", "name": "Türkiye"},
    {"country_code": "SA", "zone": "B", "multiplier": Decimal("0.7000"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Saudi Arabia"},
    {"country_code": "IL", "zone": "A", "multiplier": Decimal("0.9000"), "tax_rate": Decimal("0.1700"), "tax_code": "VAT", "name": "Israel"},
    {"country_code": "PL", "zone": "A", "multiplier": Decimal("0.5500"), "tax_rate": Decimal("0.2300"), "tax_code": "VAT", "name": "Poland"},
    {"country_code": "ES", "zone": "A", "multiplier": Decimal("0.8500"), "tax_rate": Decimal("0.2100"), "tax_code": "IVA", "name": "Spain"},
    {"country_code": "IT", "zone": "A", "multiplier": Decimal("0.8800"), "tax_rate": Decimal("0.2200"), "tax_code": "IVA", "name": "Italy"},
    {"country_code": "NL", "zone": "A", "multiplier": Decimal("0.9500"), "tax_rate": Decimal("0.2100"), "tax_code": "BTW", "name": "Netherlands"},
    {"country_code": "SE", "zone": "A", "multiplier": Decimal("1.0500"), "tax_rate": Decimal("0.2500"), "tax_code": "VAT", "name": "Sweden"},
    {"country_code": "NZ", "zone": "A", "multiplier": Decimal("0.9000"), "tax_rate": Decimal("0.1500"), "tax_code": "GST", "name": "New Zealand"},
    {"country_code": "PT", "zone": "A", "multiplier": Decimal("0.7500"), "tax_rate": Decimal("0.2300"), "tax_code": "IVA", "name": "Portugal"},
    # Wave 30 — broad curated depth. Every country below otherwise fell back to a
    # neutral 1.0× Zone-B default (expand_seed_to_all_countries), i.e. US price
    # parity — actively wrong for lower-income markets. These are indicative 2024
    # income-banded PPP multipliers + standard VAT/GST rates; operators override
    # per country in the control plane.
    # --- Europe (remaining EU/EEA + Balkans/CIS) ---
    {"country_code": "IE", "zone": "A", "multiplier": Decimal("0.9500"), "tax_rate": Decimal("0.2300"), "tax_code": "VAT", "name": "Ireland"},
    {"country_code": "BE", "zone": "A", "multiplier": Decimal("0.9200"), "tax_rate": Decimal("0.2100"), "tax_code": "VAT", "name": "Belgium"},
    {"country_code": "CH", "zone": "A", "multiplier": Decimal("1.0500"), "tax_rate": Decimal("0.0810"), "tax_code": "VAT", "name": "Switzerland"},
    {"country_code": "AT", "zone": "A", "multiplier": Decimal("0.9200"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "Austria"},
    {"country_code": "NO", "zone": "A", "multiplier": Decimal("1.0500"), "tax_rate": Decimal("0.2500"), "tax_code": "VAT", "name": "Norway"},
    {"country_code": "DK", "zone": "A", "multiplier": Decimal("1.0000"), "tax_rate": Decimal("0.2500"), "tax_code": "VAT", "name": "Denmark"},
    {"country_code": "FI", "zone": "A", "multiplier": Decimal("0.9500"), "tax_rate": Decimal("0.2550"), "tax_code": "VAT", "name": "Finland"},
    {"country_code": "IS", "zone": "A", "multiplier": Decimal("1.0500"), "tax_rate": Decimal("0.2400"), "tax_code": "VAT", "name": "Iceland"},
    {"country_code": "LU", "zone": "A", "multiplier": Decimal("1.0000"), "tax_rate": Decimal("0.1700"), "tax_code": "VAT", "name": "Luxembourg"},
    {"country_code": "GR", "zone": "A", "multiplier": Decimal("0.7000"), "tax_rate": Decimal("0.2400"), "tax_code": "VAT", "name": "Greece"},
    {"country_code": "CZ", "zone": "A", "multiplier": Decimal("0.6000"), "tax_rate": Decimal("0.2100"), "tax_code": "VAT", "name": "Czechia"},
    {"country_code": "SK", "zone": "A", "multiplier": Decimal("0.6000"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "Slovakia"},
    {"country_code": "SI", "zone": "A", "multiplier": Decimal("0.7000"), "tax_rate": Decimal("0.2200"), "tax_code": "VAT", "name": "Slovenia"},
    {"country_code": "HR", "zone": "A", "multiplier": Decimal("0.6000"), "tax_rate": Decimal("0.2500"), "tax_code": "VAT", "name": "Croatia"},
    {"country_code": "HU", "zone": "A", "multiplier": Decimal("0.5500"), "tax_rate": Decimal("0.2700"), "tax_code": "VAT", "name": "Hungary"},
    {"country_code": "LT", "zone": "A", "multiplier": Decimal("0.6500"), "tax_rate": Decimal("0.2100"), "tax_code": "VAT", "name": "Lithuania"},
    {"country_code": "LV", "zone": "A", "multiplier": Decimal("0.6500"), "tax_rate": Decimal("0.2100"), "tax_code": "VAT", "name": "Latvia"},
    {"country_code": "EE", "zone": "A", "multiplier": Decimal("0.6500"), "tax_rate": Decimal("0.2200"), "tax_code": "VAT", "name": "Estonia"},
    {"country_code": "RO", "zone": "B", "multiplier": Decimal("0.5000"), "tax_rate": Decimal("0.1900"), "tax_code": "VAT", "name": "Romania"},
    {"country_code": "BG", "zone": "B", "multiplier": Decimal("0.5000"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "Bulgaria"},
    {"country_code": "RS", "zone": "B", "multiplier": Decimal("0.4500"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "Serbia"},
    {"country_code": "UA", "zone": "B", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "Ukraine"},
    {"country_code": "RU", "zone": "B", "multiplier": Decimal("0.4500"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "Russia"},
    # --- MENA / Gulf ---
    {"country_code": "QA", "zone": "B", "multiplier": Decimal("0.8000"), "tax_rate": Decimal("0.0000"), "tax_code": "", "name": "Qatar"},
    {"country_code": "KW", "zone": "B", "multiplier": Decimal("0.8000"), "tax_rate": Decimal("0.0000"), "tax_code": "", "name": "Kuwait"},
    {"country_code": "BH", "zone": "B", "multiplier": Decimal("0.7500"), "tax_rate": Decimal("0.1000"), "tax_code": "VAT", "name": "Bahrain"},
    {"country_code": "OM", "zone": "B", "multiplier": Decimal("0.7000"), "tax_rate": Decimal("0.0500"), "tax_code": "VAT", "name": "Oman"},
    {"country_code": "JO", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.1600"), "tax_code": "GST", "name": "Jordan"},
    {"country_code": "LB", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1100"), "tax_code": "VAT", "name": "Lebanon"},
    {"country_code": "IQ", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.0000"), "tax_code": "", "name": "Iraq"},
    {"country_code": "IR", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.0900"), "tax_code": "VAT", "name": "Iran"},
    {"country_code": "DZ", "zone": "B", "multiplier": Decimal("0.3800"), "tax_rate": Decimal("0.1900"), "tax_code": "VAT", "name": "Algeria"},
    {"country_code": "TN", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1900"), "tax_code": "VAT", "name": "Tunisia"},
    {"country_code": "LY", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.0000"), "tax_code": "", "name": "Libya"},
    {"country_code": "YE", "zone": "C", "multiplier": Decimal("0.2500"), "tax_rate": Decimal("0.0500"), "tax_code": "GST", "name": "Yemen"},
    # --- Asia / Pacific ---
    {"country_code": "LK", "zone": "C", "multiplier": Decimal("0.2800"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Sri Lanka"},
    {"country_code": "NP", "zone": "C", "multiplier": Decimal("0.2500"), "tax_rate": Decimal("0.1300"), "tax_code": "VAT", "name": "Nepal"},
    {"country_code": "MM", "zone": "C", "multiplier": Decimal("0.2800"), "tax_rate": Decimal("0.0500"), "tax_code": "CT", "name": "Myanmar"},
    {"country_code": "KH", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1000"), "tax_code": "VAT", "name": "Cambodia"},
    {"country_code": "LA", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1000"), "tax_code": "VAT", "name": "Laos"},
    {"country_code": "MN", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.1000"), "tax_code": "VAT", "name": "Mongolia"},
    {"country_code": "KZ", "zone": "B", "multiplier": Decimal("0.4500"), "tax_rate": Decimal("0.1200"), "tax_code": "VAT", "name": "Kazakhstan"},
    {"country_code": "UZ", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1200"), "tax_code": "VAT", "name": "Uzbekistan"},
    {"country_code": "AZ", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Azerbaijan"},
    {"country_code": "GE", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Georgia"},
    {"country_code": "AM", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "Armenia"},
    {"country_code": "BN", "zone": "A", "multiplier": Decimal("0.7500"), "tax_rate": Decimal("0.0000"), "tax_code": "", "name": "Brunei"},
    {"country_code": "MV", "zone": "B", "multiplier": Decimal("0.5000"), "tax_rate": Decimal("0.0800"), "tax_code": "GST", "name": "Maldives"},
    {"country_code": "BT", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.0000"), "tax_code": "", "name": "Bhutan"},
    {"country_code": "AF", "zone": "C", "multiplier": Decimal("0.2200"), "tax_rate": Decimal("0.1000"), "tax_code": "BRT", "name": "Afghanistan"},
    {"country_code": "PG", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1000"), "tax_code": "GST", "name": "Papua New Guinea"},
    {"country_code": "FJ", "zone": "B", "multiplier": Decimal("0.4500"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Fiji"},
    # --- Latin America / Caribbean ---
    {"country_code": "EC", "zone": "B", "multiplier": Decimal("0.4500"), "tax_rate": Decimal("0.1500"), "tax_code": "IVA", "name": "Ecuador"},
    {"country_code": "BO", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1300"), "tax_code": "IVA", "name": "Bolivia"},
    {"country_code": "PY", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.1000"), "tax_code": "IVA", "name": "Paraguay"},
    {"country_code": "UY", "zone": "B", "multiplier": Decimal("0.5500"), "tax_rate": Decimal("0.2200"), "tax_code": "IVA", "name": "Uruguay"},
    {"country_code": "VE", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1600"), "tax_code": "IVA", "name": "Venezuela"},
    {"country_code": "GT", "zone": "C", "multiplier": Decimal("0.3800"), "tax_rate": Decimal("0.1200"), "tax_code": "IVA", "name": "Guatemala"},
    {"country_code": "HN", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1500"), "tax_code": "ISV", "name": "Honduras"},
    {"country_code": "SV", "zone": "C", "multiplier": Decimal("0.3800"), "tax_rate": Decimal("0.1300"), "tax_code": "IVA", "name": "El Salvador"},
    {"country_code": "NI", "zone": "C", "multiplier": Decimal("0.3200"), "tax_rate": Decimal("0.1500"), "tax_code": "IVA", "name": "Nicaragua"},
    {"country_code": "CR", "zone": "B", "multiplier": Decimal("0.5000"), "tax_rate": Decimal("0.1300"), "tax_code": "IVA", "name": "Costa Rica"},
    {"country_code": "PA", "zone": "B", "multiplier": Decimal("0.5500"), "tax_rate": Decimal("0.0700"), "tax_code": "ITBMS", "name": "Panama"},
    {"country_code": "DO", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.1800"), "tax_code": "ITBIS", "name": "Dominican Republic"},
    {"country_code": "JM", "zone": "B", "multiplier": Decimal("0.4500"), "tax_rate": Decimal("0.1500"), "tax_code": "GCT", "name": "Jamaica"},
    {"country_code": "TT", "zone": "B", "multiplier": Decimal("0.5000"), "tax_rate": Decimal("0.1250"), "tax_code": "VAT", "name": "Trinidad and Tobago"},
    {"country_code": "HT", "zone": "C", "multiplier": Decimal("0.2500"), "tax_rate": Decimal("0.1000"), "tax_code": "TCA", "name": "Haiti"},
    # --- Sub-Saharan Africa (broad depth) ---
    {"country_code": "ZM", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1600"), "tax_code": "VAT", "name": "Zambia"},
    {"country_code": "ZW", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Zimbabwe"},
    {"country_code": "MW", "zone": "C", "multiplier": Decimal("0.2500"), "tax_rate": Decimal("0.1650"), "tax_code": "VAT", "name": "Malawi"},
    {"country_code": "MZ", "zone": "C", "multiplier": Decimal("0.2800"), "tax_rate": Decimal("0.1600"), "tax_code": "VAT", "name": "Mozambique"},
    {"country_code": "AO", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1400"), "tax_code": "VAT", "name": "Angola"},
    {"country_code": "BW", "zone": "B", "multiplier": Decimal("0.4500"), "tax_rate": Decimal("0.1400"), "tax_code": "VAT", "name": "Botswana"},
    {"country_code": "NA", "zone": "B", "multiplier": Decimal("0.4500"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Namibia"},
    {"country_code": "MU", "zone": "B", "multiplier": Decimal("0.5000"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Mauritius"},
    {"country_code": "BJ", "zone": "C", "multiplier": Decimal("0.3200"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Benin"},
    {"country_code": "TG", "zone": "C", "multiplier": Decimal("0.3200"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Togo"},
    {"country_code": "BF", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Burkina Faso"},
    {"country_code": "ML", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Mali"},
    {"country_code": "NE", "zone": "C", "multiplier": Decimal("0.2800"), "tax_rate": Decimal("0.1900"), "tax_code": "VAT", "name": "Niger"},
    {"country_code": "GN", "zone": "C", "multiplier": Decimal("0.2800"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Guinea"},
    {"country_code": "MG", "zone": "C", "multiplier": Decimal("0.2500"), "tax_rate": Decimal("0.2000"), "tax_code": "VAT", "name": "Madagascar"},
    {"country_code": "CD", "zone": "C", "multiplier": Decimal("0.2800"), "tax_rate": Decimal("0.1600"), "tax_code": "VAT", "name": "DR Congo"},
    {"country_code": "CG", "zone": "C", "multiplier": Decimal("0.3200"), "tax_rate": Decimal("0.1890"), "tax_code": "VAT", "name": "Congo"},
    {"country_code": "GA", "zone": "B", "multiplier": Decimal("0.4000"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Gabon"},
    {"country_code": "SD", "zone": "C", "multiplier": Decimal("0.2500"), "tax_rate": Decimal("0.1700"), "tax_code": "VAT", "name": "Sudan"},
    {"country_code": "SL", "zone": "C", "multiplier": Decimal("0.2500"), "tax_rate": Decimal("0.1500"), "tax_code": "GST", "name": "Sierra Leone"},
    {"country_code": "LR", "zone": "C", "multiplier": Decimal("0.2500"), "tax_rate": Decimal("0.1000"), "tax_code": "GST", "name": "Liberia"},
    {"country_code": "GM", "zone": "C", "multiplier": Decimal("0.2800"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Gambia"},
    {"country_code": "BI", "zone": "C", "multiplier": Decimal("0.2200"), "tax_rate": Decimal("0.1800"), "tax_code": "VAT", "name": "Burundi"},
    {"country_code": "SZ", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Eswatini"},
    {"country_code": "LS", "zone": "C", "multiplier": Decimal("0.3500"), "tax_rate": Decimal("0.1500"), "tax_code": "VAT", "name": "Lesotho"},
    {"country_code": "MR", "zone": "C", "multiplier": Decimal("0.3000"), "tax_rate": Decimal("0.1600"), "tax_code": "VAT", "name": "Mauritania"},
)


def seed_country_multipliers(
    *,
    country_codes: list[str] | None = None,
    using: str = "default",
) -> dict[str, int]:
    """Upsert ``CountryMultiplier`` rows from :data:`COUNTRY_MULTIPLIER_SEED_ROWS`."""
    from django.apps import apps

    CountryMultiplier = apps.get_model("siteconfig", "CountryMultiplier")

    wanted = {
        str(row["country_code"]).strip().upper()
        for row in COUNTRY_MULTIPLIER_SEED_ROWS
    }
    if country_codes:
        normalized: set[str] = set()
        for code in country_codes:
            alpha2 = GlobalGeoCatalog.alpha2_for_country(code)
            if alpha2:
                normalized.add(alpha2.upper())
        wanted &= normalized

    created = 0
    updated = 0
    for row in COUNTRY_MULTIPLIER_SEED_ROWS:
        code = row["country_code"].upper()
        if code not in wanted:
            continue
        _, was_created = CountryMultiplier.objects.using(using).update_or_create(
            country_code=code,
            defaults={
                "zone": row["zone"],
                "multiplier": row["multiplier"],
                "tax_rate": row["tax_rate"],
                "tax_code": row["tax_code"],
                "name": row["name"],
                "is_active": True,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return {"created": created, "updated": updated, "source": PPP_SEED_SOURCE}


def all_catalog_country_codes() -> list[str]:
    """ISO alpha-2 codes from the global geo catalog (for --all expansion)."""
    codes: list[str] = []
    for item in GlobalGeoCatalog.list_countries():
        raw = str(item.get("code") or "").strip().upper()
        if not raw:
            continue
        if len(raw) == 2:
            codes.append(raw)
        elif len(raw) == 3:
            alpha2 = GlobalGeoCatalog.alpha2_for_country(raw)
            if alpha2:
                codes.append(alpha2)
    return sorted(set(codes))


def _catalog_country_names() -> dict[str, str]:
    """ISO alpha-2 -> display name from the global geo catalog (best-effort)."""
    names: dict[str, str] = {}
    for item in GlobalGeoCatalog.list_countries():
        code = str(item.get("code_alpha2") or item.get("code") or "").strip().upper()
        if len(code) == 2 and item.get("name"):
            names[code] = str(item["name"])
    return names


def expand_seed_to_all_countries(*, using: str = "default") -> dict[str, Any]:
    """Seed curated rows, then default 1.0× Zone B for every catalog country missing a row.

    Backfilled rows carry the catalog country name so operators see a readable list
    rather than blank rows; multiplier/tax stay at the neutral default until an
    operator (or a richer seed) tunes the country in the control plane.
    """
    from django.apps import apps

    CountryMultiplier = apps.get_model("siteconfig", "CountryMultiplier")

    summary = seed_country_multipliers(using=using)
    names = _catalog_country_names()
    backfilled = 0
    for code in all_catalog_country_codes():
        if CountryMultiplier.objects.using(using).filter(country_code__iexact=code).exists():
            continue
        CountryMultiplier.objects.using(using).create(
            country_code=code,
            zone="B",
            multiplier=Decimal("1.0000"),
            tax_rate=Decimal("0.0000"),
            tax_code="",
            name=names.get(code, ""),
            is_active=True,
        )
        backfilled += 1
    summary["backfilled_default"] = backfilled
    return summary
