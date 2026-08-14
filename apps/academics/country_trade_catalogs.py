"""Curated per-country TVET / vocational trade catalogs.

The platform carried NO trade/specialty catalog anywhere — a technical/vocational
school's trades (Welding, Plumbing, Catering, …) only ever arrived from an
uploaded migration file, so a TVET school onboarding fresh (or a roster-only
export that never listed its trades) landed with a single "General" specialty and
no way to place students on a course of study. This module gives a vocational
school a country-appropriate DEFAULT set of trades so it is running on day one
and merely trims/renames, never builds from scratch.

Structure: per country, a list of ``(department_name, [trade_name, …])`` groups.
A generic set covers vocational schools in countries without a curated list, so
NO TVET school is ever left with zero trades. Tenants override via
``School.settings['trade_catalog']``. A DEFAULT, never a lock — every Department
and Specialty it creates is a plain admin-editable row.

Institution-type gated by the caller: only schools that read as vocational (TVET /
technical / trade / polytechnic) get trades seeded — a general-ed school keeps its
academic subjects and never sprouts a welding specialty.
"""

from __future__ import annotations

# country (ISO alpha-2) -> [(department, [trades...]), ...]
_TRADE_CATALOGS: dict[str, list[tuple[str, list[str]]]] = {
    # Cameroon TVET (MINEFOP / technical-education trades) — representative,
    # admin-editable.
    "CM": [
        ("Building & Civil Engineering",
         ["Masonry & Concrete Works", "Carpentry & Joinery", "Plumbing & Pipe Fitting",
          "Building Construction"]),
        ("Mechanical Engineering",
         ["Welding & Metal Fabrication", "Automobile Mechanics", "Machining & Fitting"]),
        ("Electrical & Electronics",
         ["Electrical Installation & Maintenance", "Electronics",
          "Refrigeration & Air Conditioning"]),
        ("Business & Commerce",
         ["Accounting", "Secretarial & Office Practice", "Marketing & Sales"]),
        ("Home Economics & Hospitality",
         ["Catering & Hotel Management", "Fashion & Clothing Technology",
          "Cosmetology & Hairdressing"]),
        ("Information & Communication Technology",
         ["Computer Maintenance & Networking", "Software & Web Design"]),
        ("Agriculture",
         ["Crop Production", "Animal Husbandry"]),
    ],
}

# Universal fallback for any vocational school whose country has no curated list.
_GENERIC_TVET_TRADES: list[tuple[str, list[str]]] = [
    ("Building & Construction",
     ["Masonry", "Carpentry & Joinery", "Plumbing", "Building Construction"]),
    ("Mechanical & Automotive",
     ["Welding & Metal Fabrication", "Automobile Mechanics"]),
    ("Electrical & Electronics",
     ["Electrical Installation", "Electronics"]),
    ("Business & ICT",
     ["Accounting", "Office Practice", "Computer Maintenance"]),
    ("Home Economics",
     ["Catering & Hospitality", "Fashion & Tailoring", "Cosmetology"]),
    ("Agriculture",
     ["Crop Production", "Animal Husbandry"]),
]


def _normalize_catalog(raw) -> list[tuple[str, list[str]]] | None:
    """Coerce a raw catalog (curated tuple list, or a tenant override that may be
    a list of ``[dept, [trades]]`` or dicts) into ``[(dept, [trades]), …]``.
    Returns ``None`` when the shape is unusable."""
    if not isinstance(raw, (list, tuple)) or not raw:
        return None
    out: list[tuple[str, list[str]]] = []
    for group in raw:
        dept = None
        trades = None
        if isinstance(group, dict):
            dept = group.get("department") or group.get("dept")
            trades = group.get("trades") or group.get("specialties")
        elif isinstance(group, (list, tuple)) and len(group) == 2:
            dept, trades = group
        if not dept or not isinstance(trades, (list, tuple)):
            continue
        names = [str(t).strip() for t in trades if str(t).strip()]
        if names:
            out.append((str(dept).strip(), names))
    return out or None


def resolve_trade_catalog(school) -> list[tuple[str, list[str]]] | None:
    """Return the trade catalog for a (vocational) school, or ``None``.

    Cascade: per-school ``settings['trade_catalog']`` override → curated
    ``_TRADE_CATALOGS[country]`` → the universal generic TVET set. The caller is
    responsible for the institution-type gate; this always returns a non-empty
    catalog for a vocational school so none starts from scratch."""
    settings_map = getattr(school, "settings", None) or {}
    override = _normalize_catalog(settings_map.get("trade_catalog"))
    if override:
        return override

    iso = (getattr(school, "country_code", None) or "").strip().upper()[:2]
    curated = _normalize_catalog(_TRADE_CATALOGS.get(iso))
    if curated:
        return curated

    return _normalize_catalog(_GENERIC_TVET_TRADES)
