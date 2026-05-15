"""Country + education-system registry for the Migration Cloud.

A migration is *holistic* only when the platform knows the destination
country's conventions: how grade scales work, what the academic year
boundaries are, what name order is cultural default, which national ID
schemes appear in identity fields, what currency is local, what
attendance codes a registrar uses. This module ships those conventions
as a data registry so transformers, classifiers, and landers can adapt
per-tenant.

Public surface::

    get_country_profile("US")           → CountryProfile dataclass
    get_country_profile("FR")
    list_supported_countries()          → list of ISO 3166-1 alpha-2 codes
    grading_scale("UK_A_STAR")          → ScaleMap (label → canonical)
    list_grading_scales()               → list of scale slugs

Tenants override via ``RuntimeDefaults.payload['migration_cloud.country_overrides']``
(same cascade as the synonym overlay) — never via code edits in this
file. New countries are an additive change; never delete a code (a
historical bundle from that region must remain rerunnable).

ISO 3166-1 alpha-2 country codes. Languages are BCP-47 prefix-matched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# --- Education-system profile ----------------------------------------------

@dataclass(frozen=True)
class CountryProfile:
    """One country's school-data conventions.

    All fields are best-effort defaults; tenants can override via
    ``RuntimeDefaults`` (see module docstring). The migration pipeline
    consults this profile to (a) set a sane ``locale_hints['date_format']``,
    (b) pick a grading scale shortlist for the AI tiebreaker, (c)
    suggest a name-split variant, (d) default a currency.
    """

    code: str                                       # ISO 3166-1 alpha-2
    label: str
    default_language: str                           # BCP-47 short
    date_format: str                                # strptime format
    name_order: str                                 # "first_last" | "last_first" | "spanish_double"
    grading_scales: tuple[str, ...] = ()            # ordered by likelihood
    currency: str = "USD"
    academic_year_start_month: int = 9              # ISO month 1..12
    student_id_patterns: tuple[str, ...] = ()       # regex patterns for typical national/SIS IDs
    attendance_code_dialect: str = "letters_paie"   # see ATTENDANCE_DIALECTS below
    notes: str = ""


COUNTRY_PROFILES: dict[str, CountryProfile] = {
    # ------------------------------------------------------------- Americas
    "US": CountryProfile(
        code="US", label="United States", default_language="en",
        date_format="%m/%d/%Y", name_order="first_last",
        grading_scales=("US_LETTER", "US_GPA_4_0", "PERCENT_0_100"),
        currency="USD", academic_year_start_month=8,
        student_id_patterns=(r"^\d{6,10}$", r"^[A-Z]{2}-\d{4,8}$"),
        attendance_code_dialect="letters_paie",
        notes="Common SIS: PowerSchool, Infinite Campus, Skyward, Aeries, FACTS.",
    ),
    "CA": CountryProfile(
        code="CA", label="Canada", default_language="en",
        date_format="%Y-%m-%d", name_order="first_last",
        grading_scales=("CA_PERCENT", "US_LETTER", "PERCENT_0_100"),
        currency="CAD", academic_year_start_month=9,
        student_id_patterns=(r"^\d{9,10}$",),
    ),
    "MX": CountryProfile(
        code="MX", label="Mexico", default_language="es",
        date_format="%d/%m/%Y", name_order="spanish_double",
        grading_scales=("MX_0_10", "PERCENT_0_100"),
        currency="MXN", academic_year_start_month=8,
        student_id_patterns=(r"^\d{18}$",),  # CURP
        attendance_code_dialect="letters_es_pt",
    ),
    "BR": CountryProfile(
        code="BR", label="Brazil", default_language="pt",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("BR_0_10", "PERCENT_0_100"),
        currency="BRL", academic_year_start_month=2,
        student_id_patterns=(r"^\d{11}$",),  # CPF
        attendance_code_dialect="letters_es_pt",
    ),
    "AR": CountryProfile(
        code="AR", label="Argentina", default_language="es",
        date_format="%d/%m/%Y", name_order="spanish_double",
        grading_scales=("AR_0_10", "PERCENT_0_100"),
        currency="ARS", academic_year_start_month=3,
        attendance_code_dialect="letters_es_pt",
    ),
    "CL": CountryProfile(
        code="CL", label="Chile", default_language="es",
        date_format="%d-%m-%Y", name_order="spanish_double",
        grading_scales=("CL_1_7", "PERCENT_0_100"),
        currency="CLP", academic_year_start_month=3,
        attendance_code_dialect="letters_es_pt",
    ),
    "CO": CountryProfile(
        code="CO", label="Colombia", default_language="es",
        date_format="%d/%m/%Y", name_order="spanish_double",
        grading_scales=("CO_0_5", "PERCENT_0_100"),
        currency="COP", academic_year_start_month=2,
        attendance_code_dialect="letters_es_pt",
    ),
    # ------------------------------------------------------------- Europe
    "GB": CountryProfile(
        code="GB", label="United Kingdom", default_language="en",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("UK_A_STAR", "UK_GCSE_9_1", "PERCENT_0_100"),
        currency="GBP", academic_year_start_month=9,
        student_id_patterns=(r"^[A-Z]\d{12}$",),  # UPN
        notes="UPN format: 13 chars (1 letter + 12 digits).",
    ),
    "IE": CountryProfile(
        code="IE", label="Ireland", default_language="en",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("IE_LEAVING_CERT", "PERCENT_0_100"),
        currency="EUR", academic_year_start_month=9,
    ),
    "FR": CountryProfile(
        code="FR", label="France", default_language="fr",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("FR_0_20",),
        currency="EUR", academic_year_start_month=9,
        attendance_code_dialect="letters_fr",
        notes="Bulletin scolaire grading is /20.",
    ),
    "DE": CountryProfile(
        code="DE", label="Germany", default_language="de",
        date_format="%d.%m.%Y", name_order="first_last",
        grading_scales=("DE_1_6", "DE_PUNKTE_15"),
        currency="EUR", academic_year_start_month=8,
        attendance_code_dialect="letters_de",
        notes="Abitur uses Punkte 0-15 in Oberstufe; lower grades use 1-6.",
    ),
    "IT": CountryProfile(
        code="IT", label="Italy", default_language="it",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("IT_0_10", "PERCENT_0_100"),
        currency="EUR", academic_year_start_month=9,
        attendance_code_dialect="letters_es_pt",
    ),
    "ES": CountryProfile(
        code="ES", label="Spain", default_language="es",
        date_format="%d/%m/%Y", name_order="spanish_double",
        grading_scales=("ES_0_10", "PERCENT_0_100"),
        currency="EUR", academic_year_start_month=9,
        attendance_code_dialect="letters_es_pt",
    ),
    "PT": CountryProfile(
        code="PT", label="Portugal", default_language="pt",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("PT_0_20", "PERCENT_0_100"),
        currency="EUR", academic_year_start_month=9,
        attendance_code_dialect="letters_es_pt",
    ),
    "NL": CountryProfile(
        code="NL", label="Netherlands", default_language="nl",
        date_format="%d-%m-%Y", name_order="first_last",
        grading_scales=("NL_1_10",),
        currency="EUR", academic_year_start_month=9,
    ),
    "RU": CountryProfile(
        code="RU", label="Russia", default_language="ru",
        date_format="%d.%m.%Y", name_order="first_last",
        grading_scales=("RU_2_5",),
        currency="RUB", academic_year_start_month=9,
    ),
    "TR": CountryProfile(
        code="TR", label="Türkiye", default_language="tr",
        date_format="%d.%m.%Y", name_order="first_last",
        grading_scales=("TR_0_100", "PERCENT_0_100"),
        currency="TRY", academic_year_start_month=9,
    ),
    # ------------------------------------------------------- Middle East
    "AE": CountryProfile(
        code="AE", label="United Arab Emirates", default_language="ar",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("PERCENT_0_100",),
        currency="AED", academic_year_start_month=9,
    ),
    "SA": CountryProfile(
        code="SA", label="Saudi Arabia", default_language="ar",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("PERCENT_0_100",),
        currency="SAR", academic_year_start_month=8,
    ),
    "IL": CountryProfile(
        code="IL", label="Israel", default_language="he",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("IL_0_100",),
        currency="ILS", academic_year_start_month=9,
    ),
    # ------------------------------------------------------- Asia
    "IN": CountryProfile(
        code="IN", label="India", default_language="hi",
        date_format="%d-%m-%Y", name_order="first_last",
        grading_scales=("IN_CBSE_PCT", "IN_ICSE_PCT", "PERCENT_0_100", "US_GPA_4_0"),
        currency="INR", academic_year_start_month=4,
        student_id_patterns=(r"^\d{12}$",),  # Aadhaar
        notes="CBSE/ICSE percentage; some IB schools use IB_1_7.",
    ),
    "PK": CountryProfile(
        code="PK", label="Pakistan", default_language="ur",
        date_format="%d-%m-%Y", name_order="first_last",
        grading_scales=("PK_PERCENT", "PERCENT_0_100"),
        currency="PKR", academic_year_start_month=4,
    ),
    "BD": CountryProfile(
        code="BD", label="Bangladesh", default_language="bn",
        date_format="%d-%m-%Y", name_order="first_last",
        grading_scales=("BD_GPA_5", "PERCENT_0_100"),
        currency="BDT", academic_year_start_month=1,
    ),
    "CN": CountryProfile(
        code="CN", label="China", default_language="zh",
        date_format="%Y-%m-%d", name_order="last_first",
        grading_scales=("CN_PERCENT", "PERCENT_0_100"),
        currency="CNY", academic_year_start_month=9,
        attendance_code_dialect="cjk_attendance",
    ),
    "JP": CountryProfile(
        code="JP", label="Japan", default_language="ja",
        date_format="%Y/%m/%d", name_order="last_first",
        grading_scales=("JP_5_POINT", "PERCENT_0_100"),
        currency="JPY", academic_year_start_month=4,
        attendance_code_dialect="cjk_attendance",
    ),
    "KR": CountryProfile(
        code="KR", label="South Korea", default_language="ko",
        date_format="%Y-%m-%d", name_order="last_first",
        grading_scales=("KR_9_GRADE", "PERCENT_0_100"),
        currency="KRW", academic_year_start_month=3,
        attendance_code_dialect="cjk_attendance",
    ),
    "VN": CountryProfile(
        code="VN", label="Vietnam", default_language="vi",
        date_format="%d/%m/%Y", name_order="last_first",
        grading_scales=("VN_0_10", "PERCENT_0_100"),
        currency="VND", academic_year_start_month=9,
    ),
    "ID": CountryProfile(
        code="ID", label="Indonesia", default_language="id",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("ID_0_100", "PERCENT_0_100"),
        currency="IDR", academic_year_start_month=7,
    ),
    "PH": CountryProfile(
        code="PH", label="Philippines", default_language="en",
        date_format="%m/%d/%Y", name_order="first_last",
        grading_scales=("PH_DEPED",),
        currency="PHP", academic_year_start_month=8,
    ),
    "TH": CountryProfile(
        code="TH", label="Thailand", default_language="th",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("TH_0_4",),
        currency="THB", academic_year_start_month=5,
    ),
    # ------------------------------------------------------- Africa
    "ZA": CountryProfile(
        code="ZA", label="South Africa", default_language="en",
        date_format="%Y/%m/%d", name_order="first_last",
        grading_scales=("ZA_PERCENT", "PERCENT_0_100"),
        currency="ZAR", academic_year_start_month=1,
    ),
    "NG": CountryProfile(
        code="NG", label="Nigeria", default_language="en",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("NG_WAEC", "PERCENT_0_100"),
        currency="NGN", academic_year_start_month=9,
        notes="WAEC grading A1-F9 common in secondary.",
    ),
    "KE": CountryProfile(
        code="KE", label="Kenya", default_language="sw",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("KE_KCSE", "PERCENT_0_100"),
        currency="KES", academic_year_start_month=1,
    ),
    "GH": CountryProfile(
        code="GH", label="Ghana", default_language="en",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("NG_WAEC", "PERCENT_0_100"),
        currency="GHS", academic_year_start_month=9,
    ),
    "CM": CountryProfile(
        code="CM", label="Cameroon", default_language="fr",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("FR_0_20", "PERCENT_0_100"),
        currency="XAF", academic_year_start_month=9,
        notes="Anglophone subsystem uses GCE A-F; Francophone uses /20.",
    ),
    "ET": CountryProfile(
        code="ET", label="Ethiopia", default_language="am",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("ET_PERCENT", "PERCENT_0_100"),
        currency="ETB", academic_year_start_month=9,
    ),
    "EG": CountryProfile(
        code="EG", label="Egypt", default_language="ar",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("EG_PERCENT", "PERCENT_0_100"),
        currency="EGP", academic_year_start_month=9,
    ),
    # ------------------------------------------------------- Oceania
    "AU": CountryProfile(
        code="AU", label="Australia", default_language="en",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("AU_A_E", "PERCENT_0_100"),
        currency="AUD", academic_year_start_month=1,
    ),
    "NZ": CountryProfile(
        code="NZ", label="New Zealand", default_language="en",
        date_format="%d/%m/%Y", name_order="first_last",
        grading_scales=("NZ_NCEA",),
        currency="NZD", academic_year_start_month=2,
    ),
}


def get_country_profile(code: str) -> CountryProfile | None:
    """Return the profile for an ISO 3166-1 alpha-2 country code (case-insensitive).

    Returns ``None`` for unknown countries — callers fall back to global
    defaults (date_format='%Y-%m-%d', name_order='first_last',
    grading_scales=('PERCENT_0_100',), currency='USD').
    """
    if not code:
        return None
    return COUNTRY_PROFILES.get(code.upper())


def list_supported_countries() -> list[str]:
    return sorted(COUNTRY_PROFILES.keys())


# --- Grading scale catalog --------------------------------------------------

# Each scale maps raw label → canonical value. Canonical is one of:
#   * A percentage 0..100 (string) when scale has a percent equivalent.
#   * A letter A/B/C/D/E/F when scale is a letter grade.
#   * A pass/fail string when binary.
# Callers feed the matching scale slug into ``grading_scale_to_canonical``
# via ``ctx.options["scale_map"]`` (or ``ctx.options["scale_slug"]`` which
# this module resolves to the underlying mapping).

GRADING_SCALES: dict[str, dict[str, str]] = {
    # US letter A-F (with +/-)
    "US_LETTER": {
        "A+": "97", "A": "93", "A-": "90",
        "B+": "87", "B": "83", "B-": "80",
        "C+": "77", "C": "73", "C-": "70",
        "D+": "67", "D": "63", "D-": "60",
        "F": "50",
    },
    # US 4.0 GPA
    "US_GPA_4_0": {
        "4.0": "A", "3.7": "A-", "3.3": "B+", "3.0": "B", "2.7": "B-",
        "2.3": "C+", "2.0": "C", "1.7": "C-", "1.3": "D+", "1.0": "D",
        "0.0": "F",
    },
    "PERCENT_0_100": {str(i): str(i) for i in range(0, 101)},
    "CA_PERCENT": {str(i): str(i) for i in range(0, 101)},

    # UK A* down (GCSE/A-Level letter system)
    "UK_A_STAR": {
        "A*": "95", "A": "85", "B": "75", "C": "65", "D": "55",
        "E": "45", "U": "0",
    },
    # UK GCSE 9-1 (post-2017)
    "UK_GCSE_9_1": {str(i): str(i) for i in range(1, 10)},
    "IE_LEAVING_CERT": {
        "H1": "90", "H2": "80", "H3": "70", "H4": "60", "H5": "50", "H6": "40",
        "H7": "30", "H8": "0",
    },

    # Continental Europe 0-20 / 0-10 / 1-6
    "FR_0_20": {str(i): str(i) for i in range(0, 21)},
    "DE_1_6": {"1": "A", "2": "B", "3": "C", "4": "D", "5": "E", "6": "F"},
    "DE_PUNKTE_15": {str(i): str(i) for i in range(0, 16)},
    "IT_0_10": {str(i): str(i) for i in range(0, 11)},
    "ES_0_10": {str(i): str(i) for i in range(0, 11)},
    "PT_0_20": {str(i): str(i) for i in range(0, 21)},
    "NL_1_10": {str(i): str(i) for i in range(1, 11)},
    "RU_2_5": {"5": "A", "4": "B", "3": "C", "2": "F"},
    "TR_0_100": {str(i): str(i) for i in range(0, 101)},

    # Latin America
    "MX_0_10": {str(i): str(i) for i in range(0, 11)},
    "BR_0_10": {str(i): str(i) for i in range(0, 11)},
    "AR_0_10": {str(i): str(i) for i in range(0, 11)},
    "CL_1_7": {f"{i:.1f}": f"{i:.1f}" for i in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]},
    "CO_0_5": {f"{i:.1f}": f"{i:.1f}" for i in [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]},

    # Asia
    "CN_PERCENT": {str(i): str(i) for i in range(0, 101)},
    "JP_5_POINT": {"5": "A", "4": "B", "3": "C", "2": "D", "1": "F"},
    "KR_9_GRADE": {str(i): str(i) for i in range(1, 10)},
    "VN_0_10": {str(i): str(i) for i in range(0, 11)},
    "ID_0_100": {str(i): str(i) for i in range(0, 101)},
    "IN_CBSE_PCT": {str(i): str(i) for i in range(0, 101)},
    "IN_ICSE_PCT": {str(i): str(i) for i in range(0, 101)},
    "BD_GPA_5": {"5.0": "A+", "4.0": "A", "3.5": "A-", "3.0": "B", "2.0": "C", "1.0": "D", "0.0": "F"},
    "PK_PERCENT": {str(i): str(i) for i in range(0, 101)},
    "PH_DEPED": {
        "90": "Outstanding", "85": "Very Satisfactory", "80": "Satisfactory",
        "75": "Fairly Satisfactory", "74": "Did Not Meet Expectations",
    },
    "TH_0_4": {"4": "A", "3.5": "B+", "3": "B", "2.5": "C+", "2": "C", "1.5": "D+", "1": "D", "0": "F"},

    # Africa
    "ZA_PERCENT": {str(i): str(i) for i in range(0, 101)},
    "NG_WAEC": {
        "A1": "90", "B2": "75", "B3": "70", "C4": "65", "C5": "60", "C6": "55",
        "D7": "45", "E8": "40", "F9": "0",
    },
    "KE_KCSE": {
        "A": "12", "A-": "11", "B+": "10", "B": "9", "B-": "8",
        "C+": "7", "C": "6", "C-": "5", "D+": "4", "D": "3", "D-": "2", "E": "1",
    },
    "ET_PERCENT": {str(i): str(i) for i in range(0, 101)},
    "EG_PERCENT": {str(i): str(i) for i in range(0, 101)},

    # IB
    "IB_1_7": {"7": "97", "6": "85", "5": "72", "4": "60", "3": "50", "2": "40", "1": "20"},

    # Israel + Middle East percentage
    "IL_0_100": {str(i): str(i) for i in range(0, 101)},

    # Oceania
    "AU_A_E": {"A": "95", "B": "80", "C": "65", "D": "50", "E": "35"},
    "NZ_NCEA": {"E": "90", "M": "75", "A": "60", "N": "0"},
}


def grading_scale(slug: str) -> dict[str, str] | None:
    """Return the mapping for a scale slug (e.g. ``"UK_A_STAR"``)."""
    if not slug:
        return None
    return GRADING_SCALES.get(slug.upper())


def list_grading_scales() -> list[str]:
    return sorted(GRADING_SCALES.keys())


# --- Attendance code dialects ----------------------------------------------

# Per-country / per-vendor attendance-code conventions, normalised to the
# canonical platform set: present|absent|late|excused|holiday|suspended.
ATTENDANCE_DIALECTS: dict[str, dict[str, str]] = {
    # P/A/L/E plus T (tardy) and E (excused) — US default.
    "letters_paie": {
        "P": "present", "PR": "present", "PRESENT": "present", "PRES": "present",
        "A": "absent", "AB": "absent", "ABS": "absent", "ABSENT": "absent",
        "L": "late", "T": "late", "TR": "late", "TARDY": "late", "LATE": "late",
        "E": "excused", "EX": "excused", "EXC": "excused", "EXCUSED": "excused",
        "H": "holiday", "HOL": "holiday", "HOLIDAY": "holiday",
        "S": "suspended", "SUS": "suspended", "SUSPENDED": "suspended",
    },
    # Anwesend/Abwesend (German)
    "letters_de": {
        "AW": "present", "ANWESEND": "present",
        "AB": "absent", "ABWESEND": "absent",
        "VS": "late", "VERSPÄTET": "late", "VERSPATET": "late",
        "EN": "excused", "ENTSCHULDIGT": "excused",
        "FE": "holiday", "FERIEN": "holiday",
    },
    # Présent/Absent (French) — also covers FR/CM/etc.
    "letters_fr": {
        "PR": "present", "PRESENT": "present", "PRÉSENT": "present",
        "AB": "absent", "ABS": "absent", "ABSENT": "absent",
        "RE": "late", "RETARD": "late",
        "EX": "excused", "EXCUSE": "excused", "EXCUSÉ": "excused",
        "CO": "holiday", "CONGE": "holiday", "CONGÉ": "holiday",
    },
    # Presente/Ausente (Spanish + Portuguese)
    "letters_es_pt": {
        "P": "present", "PR": "present", "PRESENTE": "present",
        "A": "absent", "AU": "absent", "AUSENTE": "absent",
        "T": "late", "TARDE": "late", "AT": "late", "ATRASO": "late",
        "JU": "excused", "JUSTIFICADO": "excused",
        "F": "holiday", "FERIADO": "holiday",
    },
    # 出席/欠席 (Japanese + Chinese characters)
    "cjk_attendance": {
        "出席": "present", "出": "present",
        "欠席": "absent", "欠": "absent",
        "遅刻": "late", "遅": "late", "迟到": "late",
        "病欠": "excused", "病假": "excused",
        "休日": "holiday", "假期": "holiday",
    },
    # P/A/L/E unicode + Hindi
    "letters_in": {
        "P": "present", "उपस्थित": "present",
        "A": "absent", "अनुपस्थित": "absent",
        "L": "late", "देरी": "late",
        "E": "excused", "क्षमायाचित": "excused",
    },
}


def attendance_dialect(slug: str) -> dict[str, str] | None:
    if not slug:
        return None
    return ATTENDANCE_DIALECTS.get(slug)


# --- Country override loader (tenant cascade) ------------------------------

_OVERRIDE_CACHE: dict[str, Any] | None = None


def _load_overrides() -> dict[str, Any]:
    """Read tenant/platform overrides from RuntimeDefaults. Cached for the process."""
    global _OVERRIDE_CACHE
    if _OVERRIDE_CACHE is not None:
        return _OVERRIDE_CACHE
    out: dict[str, Any] = {}
    try:
        from apps.platform_runtime.models import RuntimeDefaults

        rd = RuntimeDefaults.objects.first()
        if rd is not None:
            raw = (rd.payload or {}).get("migration_cloud.country_overrides")
            if isinstance(raw, dict):
                out = raw
    except Exception:  # noqa: BLE001
        out = {}
    _OVERRIDE_CACHE = out
    return out


def reset_country_override_cache() -> None:
    global _OVERRIDE_CACHE
    _OVERRIDE_CACHE = None


def resolved_country_profile(code: str) -> CountryProfile | None:
    """Return the country profile with any tenant overrides applied.

    Override payload shape::

        {
            "FR": {"grading_scales": ["FR_0_20", "PERCENT_0_100"], "currency": "EUR"},
            ...
        }
    """
    base = get_country_profile(code)
    if base is None:
        return None
    overrides = _load_overrides().get((code or "").upper()) if code else None
    if not isinstance(overrides, dict):
        return base

    # Replace only fields the override supplies; preserve baseline otherwise.
    return CountryProfile(
        code=base.code,
        label=str(overrides.get("label", base.label)),
        default_language=str(overrides.get("default_language", base.default_language)),
        date_format=str(overrides.get("date_format", base.date_format)),
        name_order=str(overrides.get("name_order", base.name_order)),
        grading_scales=tuple(overrides.get("grading_scales") or base.grading_scales),
        currency=str(overrides.get("currency", base.currency)),
        academic_year_start_month=int(overrides.get("academic_year_start_month", base.academic_year_start_month)),
        student_id_patterns=tuple(overrides.get("student_id_patterns") or base.student_id_patterns),
        attendance_code_dialect=str(overrides.get("attendance_code_dialect", base.attendance_code_dialect)),
        notes=str(overrides.get("notes", base.notes)),
    )
