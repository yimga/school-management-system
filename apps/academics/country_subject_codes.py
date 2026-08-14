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
