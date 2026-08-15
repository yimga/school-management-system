"""Country-standard subject-code scheme.

Gives each ``Subject`` a national / country-standard code so a school's report
cards, transcripts, and government exports carry the identifiers examiners and
ministries expect (a Cameroon GCE-style code, a national curriculum code, …)
instead of a bare name. Local-first minimum default — a four-layer cascade, the
read-side twin of the term-window cascade in ``country_term_calendars``:

    per-school   settings['subject_codes'][name]              (this school's edit)
      ▸ per-profile config['subject_codes'][name]             (region-wide, one edit)
      ▸ curated _NATIONAL_SUBJECT_CODES[country][name]        (shipped official codes)
      ▸ deterministic mnemonic fallback                       (every subject gets SOME code)

so a school is never left with code-less subjects, AND an operator can enter a
country's real official codes ONCE at the profile level and every school in that
country inherits them — no code change, no deploy (the same
``EducationSystemProfile.config`` home term windows already use). ``Subject.code``
is also a plain admin-editable string, NOT unique-enforced — a first-run default,
never a lock. Swapping in a country's real numeric board codes is a data edit.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

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

# Shared Hispanophone subject set (Spain + Spanish-speaking Latin America). Codes
# are the common abbreviations used on Spanish-language boletines.
_ES_CODES: dict[str, str] = {
    "matemáticas": "MAT", "mathematics": "MAT",
    "lengua": "LEN", "lengua y literatura": "LEN", "castellano": "LEN",
    "español": "ESP", "spanish": "ESP",
    "ciencias naturales": "CN", "biología": "BIO", "química": "QUI", "física": "FIS",
    "ciencias sociales": "CS", "historia": "HIS", "geografía": "GEO",
    "inglés": "ING", "english": "ING",
    "educación física": "EF",
    "informática": "INF", "computación": "INF",
    "filosofía": "FIL", "economía": "ECO", "contabilidad": "CON",
    "arte": "ART", "música": "MUS", "educación cívica": "CIV",
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

    # Hispanophone — Spain + Spanish-speaking Latin America (shared _ES_CODES).
    "ES": _ES_CODES, "MX": _ES_CODES, "AR": _ES_CODES, "CL": _ES_CODES,
    "CO": _ES_CODES, "PE": _ES_CODES, "VE": _ES_CODES, "EC": _ES_CODES,
    "BO": _ES_CODES, "PY": _ES_CODES, "UY": _ES_CODES, "CR": _ES_CODES,
    "NI": _ES_CODES, "HN": _ES_CODES, "GT": _ES_CODES, "SV": _ES_CODES,
    "PA": _ES_CODES, "DO": _ES_CODES, "CU": _ES_CODES,
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


def _code_from_override_map(raw, name: str) -> str:
    """Return a non-empty override code for ``name`` from a ``{name: code}`` map.

    Case-insensitive on the subject name (admins type keys however they like);
    ignores non-string / blank values. Returns ``""`` when the map supplies
    nothing usable, so callers fall through to the next cascade layer."""
    if not isinstance(raw, dict):
        return ""
    target = (name or "").strip().lower()
    if not target:
        return ""
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if key.strip().lower() == target and value.strip():
            return value.strip()
    return ""


def _profile_subject_codes(school) -> dict:
    """Return the education-system profile's ``config['subject_codes']`` map, or {}.

    Best-effort and never raises — mirrors the profile layer of
    :func:`apps.academics.country_term_calendars._lookup_windows`, so subject codes
    and term windows share ONE region-level override home
    (``EducationSystemProfile.config``)."""
    # An unsaved school cannot carry a persisted profile — short-circuit so the
    # pure-resolution paths (e.g. the country-coverage ratchet) never touch the DB.
    if getattr(getattr(school, "_state", None), "adding", True):
        return {}
    try:
        from apps.policies.policy_registry import get_effective_policy
        from apps.siteconfig.education_profile_engine import resolve_profile_for_school

        policy = get_effective_policy(school) or {}
        profile = resolve_profile_for_school(
            school,
            requested_profile_code=str(policy.get("education_profile_code") or "").strip(),
            auto_create=False,
        )
        cfg = getattr(profile, "config", None) or {}
        codes = cfg.get("subject_codes") if isinstance(cfg, dict) else None
        return codes if isinstance(codes, dict) else {}
    except Exception:  # noqa: BLE001 — profile layer is best-effort
        logger.debug("_profile_subject_codes: profile resolve failed", exc_info=True)
        return {}


def _override_code(school, name: str) -> str:
    """Return an admin/operator override code for a subject, or ``""``.

    Cascade (highest precedence first), the read-side twin of term windows:
    per-school ``settings['subject_codes']`` → per-education-system
    ``EducationSystemProfile.config['subject_codes']``."""
    settings_map = getattr(school, "settings", None)
    school_codes = settings_map.get("subject_codes") if isinstance(settings_map, dict) else None
    code = _code_from_override_map(school_codes, name)
    if code:
        return code
    return _code_from_override_map(_profile_subject_codes(school), name)


def resolve_subject_code(school, subject_name: str) -> str:
    """Return the national/standard code for a subject at a school.

    Cascade: admin/operator override (per-school ``settings['subject_codes']`` →
    per-profile ``config['subject_codes']``) → curated country table (shipped
    official codes) → deterministic mnemonic fallback. Never raises — an unknown
    country with no override simply gets the mnemonic, so every subject is always
    coded."""
    name = (subject_name or "").strip().lower()
    if not name:
        return ""
    override = _override_code(school, name)
    if override:
        return override
    iso = (getattr(school, "country_code", None) or "").strip().upper()[:2]
    table = _NATIONAL_SUBJECT_CODES.get(iso, {})
    if name in table:
        return table[name]
    return _mnemonic(subject_name)


def effective_subject_code_map(school) -> dict[str, str]:
    """Return the merged ``{subject_name: code}`` a school would resolve, by layer.

    Curated national table for the school's country, overlaid with the profile
    override, overlaid with the per-school override (each higher layer wins). Keys
    are the lowercase normalized names used throughout this module. Handy for an
    admin preview surface and for the official-catalog importer to see what a
    country already resolves. Read-only."""
    iso = (getattr(school, "country_code", None) or "").strip().upper()[:2]
    merged: dict[str, str] = {}

    def _overlay(layer) -> None:
        if not isinstance(layer, dict):
            return
        for key, value in layer.items():
            if isinstance(key, str) and isinstance(value, str) and value.strip():
                merged[key.strip().lower()] = value.strip()

    _overlay(_NATIONAL_SUBJECT_CODES.get(iso, {}))
    _overlay(_profile_subject_codes(school))
    settings_map = getattr(school, "settings", None)
    _overlay(settings_map.get("subject_codes") if isinstance(settings_map, dict) else None)
    return merged
