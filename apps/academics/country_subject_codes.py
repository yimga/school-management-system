"""Country-standard subject-code scheme.

Gives each ``Subject`` a national / country-standard code so a school's report
cards, transcripts, and government exports carry the identifiers examiners and
ministries expect (a Cameroon GCE-style code, a national curriculum code, …)
instead of a bare name. Local-first minimum default:

    curated  _NATIONAL_SUBJECT_CODES[country][name]   (official codes live here)
      ⊕ deterministic mnemonic fallback                (every subject gets SOME code)

so a school is never left with code-less subjects, and an admin refines the exact
official codes afterward. ``Subject.code`` is a plain admin-editable string, NOT
unique-enforced — a first-run default, never a lock. The curated tables are
seeded with sensible mnemonics; swapping in a country's real numeric board codes
is a data edit, not a code change.
"""

from __future__ import annotations

import re

# Shared WASSCE code set for Anglophone West Africa (WAEC-examined countries). The
# board's real per-diet numeric codes are not stable identifiers a school carries,
# so these are readable subject mnemonics an admin can replace with exact codes.
_WAEC_CODES: dict[str, str] = {
    "english language": "ENG", "english": "ENG",
    "mathematics": "MTH", "further mathematics": "FMTH",
    "biology": "BIO", "chemistry": "CHM", "physics": "PHY",
    "agricultural science": "AGRIC", "agriculture": "AGRIC",
    "economics": "ECO", "commerce": "COM", "accounting": "ACC",
    "financial accounting": "ACC", "government": "GOV",
    "geography": "GEO", "history": "HIS", "literature in english": "LIT",
    "christian religious studies": "CRS", "islamic religious studies": "IRS",
    "civic education": "CIV", "computer studies": "CMP",
    "data processing": "DP", "food and nutrition": "FDN",
    "technical drawing": "TD", "french": "FRE",
}

# Shared francophone bac subject set (France + francophone Africa). Codes are the
# common abbreviations used on francophone bulletins.
_FR_CODES: dict[str, str] = {
    "mathématiques": "MATH", "mathematics": "MATH",
    "français": "FRAN", "french": "FRAN",
    "philosophie": "PHILO", "philosophy": "PHILO",
    "histoire-géographie": "HIGE", "histoire": "HIST", "géographie": "GEOG",
    "sciences de la vie et de la terre": "SVT", "svt": "SVT",
    "physique-chimie": "PHCH", "physique": "PHYS", "chimie": "CHIM",
    "anglais": "ANGL", "english": "ANGL",
    "espagnol": "ESPA", "allemand": "ALLE",
    "éducation physique et sportive": "EPS", "eps": "EPS",
    "sciences économiques et sociales": "SES",
    "informatique": "INFO",
}

# country (ISO alpha-2) -> {normalized subject name: standard code}
_NATIONAL_SUBJECT_CODES: dict[str, dict[str, str]] = {
    # Cameroon (bilingual GCE / francophone). Mnemonic defaults — an admin can
    # replace these with the exact GCE Board / MINESEC numeric codes.
    "CM": {
        "mathematics": "MATH",
        "further mathematics": "FMTH",
        "additional mathematics": "AMTH",
        "english language": "ENGL",
        "english": "ENGL",
        "literature in english": "LITE",
        "french": "FREN",
        "french language": "FREN",
        "français": "FREN",
        "biology": "BIOL",
        "chemistry": "CHEM",
        "physics": "PHYS",
        "history": "HIST",
        "geography": "GEOG",
        "citizenship": "CITZ",
        "citizenship education": "CITZ",
        "computer science": "CMSC",
        "information technology": "ICTN",
        "economics": "ECON",
        "commerce": "COMM",
        "accounting": "ACCT",
        "religious studies": "RELS",
        "food science": "FOOD",
        "physical education": "PHED",
    },

    # Kenya — REAL KNEC / KCSE numeric subject codes.
    "KE": {
        "english": "101", "kiswahili": "102", "mathematics": "121",
        "biology": "231", "physics": "232", "chemistry": "233",
        "history and government": "311", "history": "311",
        "geography": "312",
        "christian religious education": "313", "cre": "313",
        "islamic religious education": "314", "ire": "314",
        "hindu religious education": "315",
        "home science": "441", "art and design": "442",
        "agriculture": "443", "computer studies": "451",
        "business studies": "565", "music": "511",
        "french": "701", "german": "702", "arabic": "703",
    },

    # India — REAL CBSE numeric subject codes (secondary / senior secondary).
    "IN": {
        "english": "184", "english core": "301", "hindi": "002",
        "mathematics": "041", "science": "086",
        "social science": "087",
        "physics": "042", "chemistry": "043", "biology": "044",
        "computer science": "083", "informatics practices": "065",
        "economics": "030", "business studies": "054", "accountancy": "055",
        "history": "027", "geography": "029", "political science": "028",
        "physical education": "048",
    },

    # South Africa — NSC / DBE subject mnemonics.
    "ZA": {
        "english home language": "ENGHL", "english": "ENG",
        "afrikaans": "AFR", "isizulu": "ZUL", "isixhosa": "XHO",
        "mathematics": "MATH", "mathematical literacy": "MLIT",
        "physical sciences": "PHSC", "life sciences": "LFSC",
        "life orientation": "LO", "accounting": "ACC",
        "business studies": "BUS", "economics": "ECON",
        "geography": "GEO", "history": "HIST",
        "information technology": "IT",
        "computer applications technology": "CAT",
        "tourism": "TOUR", "agricultural sciences": "AGRIC",
    },

    # United Kingdom — GCSE subject mnemonics.
    "GB": {
        "mathematics": "MATH", "english language": "ENGL",
        "english literature": "ENLI", "biology": "BIOL",
        "chemistry": "CHEM", "physics": "PHYS", "combined science": "SCI",
        "history": "HIST", "geography": "GEOG", "french": "FREN",
        "spanish": "SPAN", "german": "GERM", "computer science": "COMP",
        "religious studies": "RS", "physical education": "PE",
        "business studies": "BUS", "economics": "ECON", "art and design": "ART",
    },

    # Anglophone West Africa (WASSCE / WAEC) — shared set.
    "NG": _WAEC_CODES, "GH": _WAEC_CODES, "LR": _WAEC_CODES,
    "SL": _WAEC_CODES, "GM": _WAEC_CODES,

    # Francophone bac (France + francophone Africa) — shared set.
    "FR": _FR_CODES, "CI": _FR_CODES, "SN": _FR_CODES, "ML": _FR_CODES,
    "BF": _FR_CODES, "NE": _FR_CODES, "GN": _FR_CODES, "TG": _FR_CODES,
    "BJ": _FR_CODES, "GA": _FR_CODES, "CG": _FR_CODES, "CD": _FR_CODES,
    "TD": _FR_CODES, "CF": _FR_CODES, "BI": _FR_CODES, "DJ": _FR_CODES,
    "MG": _FR_CODES,
}


def _mnemonic(subject_name: str) -> str:
    """A deterministic, readable fallback code for any subject name.

    Single word → its first four letters (Mathematics → MATH, History → HIST);
    multi-word → the initials of its words (English Language → EL, Religious
    Studies → RS). Uppercased, alphanumerics only, capped at 8 chars. Collisions
    are allowed (``Subject.code`` is not unique)."""
    words = [w for w in re.split(r"[^0-9A-Za-z]+", subject_name or "") if w]
    if not words:
        return ""
    if len(words) == 1:
        return words[0][:4].upper()
    return "".join(w[0] for w in words[:8]).upper()


def resolve_subject_code(school, subject_name: str) -> str:
    """Return the national/standard code for a subject at a school.

    Curated country table first (official codes), then the deterministic mnemonic
    fallback. Never raises — an unknown country simply gets the mnemonic."""
    name = (subject_name or "").strip().lower()
    if not name:
        return ""
    iso = (getattr(school, "country_code", None) or "").strip().upper()[:2]
    table = _NATIONAL_SUBJECT_CODES.get(iso, {})
    if name in table:
        return table[name]
    return _mnemonic(subject_name)
