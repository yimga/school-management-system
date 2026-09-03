"""Keyword heuristics linking professional subjects to TVET specialties.

Used after import or during remediation when a subject catalog lacks an explicit
parent specialty column (common in Francophone exports).
"""

from __future__ import annotations

import re
from typing import Iterable

# (specialty code or name fragment, subject-name keyword tuples)
_PROFESSIONAL_LINK_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("EPS", ("electrical", "power", "circuit", "electronics", "energy")),
    ("ELECTRICAL", ("electrical", "power", "circuit", "electronics")),
    ("PL", ("plumbing", "water supply", "water network", "sanitary")),
    ("PLUMBING", ("plumbing", "water supply", "water network")),
    ("ARM", ("engine", "chassis", "diesel", "automotive", "motor", "vehicle")),
    ("MOTOR", ("engine", "chassis", "diesel", "automotive", "motor")),
    ("FD", ("sewing", "pattern", "fashion", "garment", "clothing", "habillement")),
    ("FASHION", ("sewing", "pattern", "fashion", "garment", "clothing")),
    ("MWIP", ("welding", "metal fab", "fabrication", "sheet metal", "chaudronnerie")),
    ("WELD", ("welding", "metal fab", "fabrication", "sheet metal")),
    ("ACCOUNTX", ("accounting", "commerce", "economics", "ohada", "business math")),
    ("ACCOUNT", ("accounting", "commerce", "economics", "ohada")),
    ("BC", ("building", "construction", "civil", "concrete", "masonry")),
    ("CIVIL", ("civil", "construction", "building", "concrete")),
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def specialty_codes_for_subject(subject_name: str, specialty_codes: Iterable[str]) -> list[str]:
    """Return specialty codes that a professional subject name likely belongs to."""
    name = _norm(subject_name)
    if not name:
        return []
    codes_upper = {c.upper() for c in specialty_codes if c}
    hits: list[str] = []
    for code_fragment, keywords in _PROFESSIONAL_LINK_RULES:
        if code_fragment not in codes_upper and not any(
            code_fragment in c for c in codes_upper
        ):
            continue
        if any(kw in name for kw in keywords):
            for c in codes_upper:
                if code_fragment in c or c.startswith(code_fragment):
                    hits.append(c)
                    break
            else:
                hits.append(code_fragment)
    return list(dict.fromkeys(hits))


def is_general_subject_name(subject_name: str, category: str | None = None) -> bool:
    cat = (category or "").strip().upper()
    if cat == "GENERAL":
        return True
    name = _norm(subject_name)
    general_markers = (
        "mathematics", "math ", "english", "french", "citizenship", "civic",
        "physical education", "sport", "history", "geography", "biology",
        "chemistry", "physics", "language",
    )
    return any(m in name for m in general_markers)
