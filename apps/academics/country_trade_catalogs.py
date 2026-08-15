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

# Shared francophone-Africa TVET set (Génie Civil / Mécanique / Électrotechnique /
# Tertiaire / Hôtellerie / Informatique / Agriculture) — used by the francophone
# West & Central African countries whose technical systems mirror the same
# ministry (MINEFOP-style) trade families. Cameroon keeps its own bilingual set.
_TVET_FR: list[tuple[str, list[str]]] = [
    ("Génie Civil & Bâtiment",
     ["Maçonnerie", "Menuiserie & Ébénisterie", "Plomberie Sanitaire",
      "Construction Bâtiment"]),
    ("Génie Mécanique",
     ["Soudure & Construction Métallique", "Mécanique Automobile", "Ajustage & Usinage"]),
    ("Électrotechnique",
     ["Installation & Maintenance Électrique", "Électronique", "Froid & Climatisation"]),
    ("Tertiaire & Gestion",
     ["Comptabilité", "Secrétariat Bureautique", "Commerce & Vente"]),
    ("Hôtellerie & Économie Familiale",
     ["Hôtellerie-Restauration", "Couture & Habillement", "Coiffure & Esthétique"]),
    ("Informatique",
     ["Maintenance Informatique & Réseaux", "Développement Web & Logiciel"]),
    ("Agriculture",
     ["Production Végétale", "Élevage"]),
]

# Shared Hispanophone TVET set (Spain + Spanish-speaking Latin America) — the same
# trade families as the francophone set, in Spanish.
_TVET_ES: list[tuple[str, list[str]]] = [
    ("Construcción",
     ["Albañilería", "Carpintería", "Instalaciones Sanitarias (Plomería)", "Edificación"]),
    ("Mecánica",
     ["Soldadura y Estructuras Metálicas", "Mecánica Automotriz", "Ajuste y Maquinado"]),
    ("Electricidad y Electrónica",
     ["Instalaciones Eléctricas", "Electrónica", "Refrigeración y Climatización"]),
    ("Administración y Comercio",
     ["Contabilidad", "Secretariado y Ofimática", "Ventas y Mercadeo"]),
    ("Hostelería y Belleza",
     ["Gastronomía y Hotelería", "Confección y Moda", "Cosmetología y Peluquería"]),
    ("Informática",
     ["Soporte y Redes Informáticas", "Desarrollo Web y Software"]),
    ("Agropecuaria",
     ["Producción Agrícola", "Producción Pecuaria"]),
]

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

    # Nigeria (NBTE technical-college trades) — representative, admin-editable.
    "NG": [
        ("Building & Woodwork",
         ["Bricklaying & Concreting", "Carpentry & Joinery", "Plumbing & Pipe Fitting",
          "Painting & Decorating"]),
        ("Mechanical Engineering Trades",
         ["Welding & Fabrication", "Motor Vehicle Mechanics", "Machining & Fitting"]),
        ("Electrical & Electronics",
         ["Electrical Installation & Maintenance", "Radio, TV & Electronics",
          "Refrigeration & Air Conditioning"]),
        ("Computer & ICT",
         ["Computer Craft & Networking", "Data Processing"]),
        ("Business & Finance",
         ["Accounting", "Office Technology & Management", "Marketing"]),
        ("Hospitality & Garment",
         ["Catering & Hotel Management", "Garment Making / Fashion Design", "Cosmetology"]),
        ("Agriculture",
         ["Crop Production", "Animal Production"]),
    ],

    # Ghana (TVET Service / CTVET trades).
    "GH": [
        ("Construction",
         ["Masonry", "Carpentry & Joinery", "Plumbing", "Painting & Decorating"]),
        ("Mechanical",
         ["Welding & Fabrication", "Auto Mechanics", "Fitting & Machining"]),
        ("Electrical",
         ["Electrical Installation", "Electronics", "Refrigeration & Air Conditioning"]),
        ("ICT",
         ["Computer Hardware & Networking", "Software & Web Design"]),
        ("Business",
         ["Accounting", "Secretarial", "Sales & Marketing"]),
        ("Hospitality & Beauty",
         ["Catering & Hospitality", "Fashion & Textiles", "Cosmetology & Beauty Therapy"]),
        ("Agriculture",
         ["General Agriculture", "Agro-Processing"]),
    ],

    # Kenya (TVETA / CDACC CBET occupations).
    "KE": [
        ("Building & Civil Engineering",
         ["Masonry", "Carpentry & Joinery", "Plumbing", "Building Technology"]),
        ("Mechanical & Automotive",
         ["Welding & Fabrication", "Automotive Engineering", "Fitter Machinist"]),
        ("Electrical & Electronics",
         ["Electrical Installation", "Electronics Technology",
          "Refrigeration & Air Conditioning"]),
        ("ICT",
         ["ICT Technician", "Computer Networking"]),
        ("Business",
         ["Accountancy", "Secretarial Studies", "Sales & Marketing"]),
        ("Hospitality & Beauty",
         ["Food & Beverage / Catering", "Fashion Design & Garment Making",
          "Hairdressing & Beauty Therapy"]),
        ("Agriculture",
         ["Crop Production", "Animal Husbandry"]),
    ],

    # South Africa (TVET College NC(V) / SETA programmes).
    "ZA": [
        ("Engineering & Related Design",
         ["Fitting & Turning", "Welding", "Motor Mechanics", "Boilermaking"]),
        ("Electrical Infrastructure Construction",
         ["Electrical", "Electronics"]),
        ("Civil Engineering & Building Construction",
         ["Bricklaying & Plastering", "Carpentry", "Plumbing"]),
        ("Information Technology & Computer Science",
         ["IT Support", "Systems Development"]),
        ("Hospitality",
         ["Professional Cookery", "Food & Beverage Services"]),
        ("Office Administration",
         ["Office Practice", "Bookkeeping"]),
    ],

    # India (ITI / NCVT engineering & non-engineering trades).
    "IN": [
        ("Engineering Trades",
         ["Fitter", "Turner", "Machinist", "Welder"]),
        ("Electrical & Electronics",
         ["Electrician", "Electronics Mechanic", "Refrigeration & Air Conditioning Technician"]),
        ("Automotive",
         ["Mechanic (Motor Vehicle)", "Mechanic Diesel"]),
        ("Construction",
         ["Draughtsman (Civil)", "Plumber", "Surveyor"]),
        ("Computer & Office",
         ["Computer Operator & Programming Assistant (COPA)", "Stenographer"]),
        ("Apparel & Hospitality",
         ["Sewing Technology", "Food Production"]),
    ],

    # Francophone West & Central Africa — shared MINEFOP-style set (_TVET_FR).
    "CI": _TVET_FR, "SN": _TVET_FR, "ML": _TVET_FR, "BF": _TVET_FR, "NE": _TVET_FR,
    "GN": _TVET_FR, "TG": _TVET_FR, "BJ": _TVET_FR, "MR": _TVET_FR, "GA": _TVET_FR,
    "CG": _TVET_FR, "CD": _TVET_FR, "TD": _TVET_FR, "CF": _TVET_FR, "GQ": _TVET_FR,
    "BI": _TVET_FR, "DJ": _TVET_FR, "MG": _TVET_FR,

    # Hispanophone — Spain + Spanish-speaking Latin America (shared _TVET_ES).
    "ES": _TVET_ES, "MX": _TVET_ES, "AR": _TVET_ES, "CL": _TVET_ES, "CO": _TVET_ES,
    "PE": _TVET_ES, "VE": _TVET_ES, "EC": _TVET_ES, "BO": _TVET_ES, "PY": _TVET_ES,
    "UY": _TVET_ES, "CR": _TVET_ES, "NI": _TVET_ES, "HN": _TVET_ES, "GT": _TVET_ES,
    "SV": _TVET_ES, "PA": _TVET_ES, "DO": _TVET_ES, "CU": _TVET_ES,
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
