"""Country -> certification exam-board availability (local-first SOT).

`CertificationExamSession.Board` is a GLOBAL enum. Presenting the full list to
every tenant means a school in the United States sees "GCE Board (Cameroon)" /
"WAEC" / "Baccalauréat (France)" — the local-first bug the owner flagged ("if
Cameroon calls an exam GCE it is not the case in the USA, so why does a US school
see GCE"). This module maps ISO-3166-1 alpha-2 country codes to the boards that
are actually relevant there, so any board-selection UI can filter choices by
`school.country_code`.

No DB, no migration: a curated constant + pure helpers, seeded/overridden the
same way `apps/siteconfig/_seed_country_localization.py` and
`apps/locale/phone_formats.py` curate per-country data. International curricula
(Cambridge IGCSE, IB) are available everywhere; an unknown or empty country
falls back to the FULL list (fail-open — never block a legitimate board just
because that country has not been curated yet).
"""
from __future__ import annotations

from apps.academics.models import CertificationExamSession

Board = CertificationExamSession.Board

# Boards offered in essentially any country (international curricula + escape hatch).
INTERNATIONAL_BOARDS = (Board.IGCSE_CIE, Board.IB, Board.OTHER)

# ISO-3166-1 alpha-2 country -> region-appropriate national/regional boards.
# International boards are unioned in automatically. Curated; extend as regions
# onboard. (West-African WAEC members share WAEC; add rows as needed.)
COUNTRY_BOARDS = {
    "CM": (Board.GCE_BOARD, Board.OBC, Board.STATE_BOARD),   # Cameroon
    "NG": (Board.WAEC, Board.NECO, Board.STATE_BOARD),       # Nigeria
    "GH": (Board.WAEC, Board.STATE_BOARD),                   # Ghana
    "SL": (Board.WAEC, Board.STATE_BOARD),                   # Sierra Leone
    "GM": (Board.WAEC, Board.STATE_BOARD),                   # The Gambia
    "LR": (Board.WAEC, Board.STATE_BOARD),                   # Liberia
    "KE": (Board.KCSE, Board.STATE_BOARD),                   # Kenya
    "US": (Board.AP_CB, Board.STATE_BOARD),                  # United States
    "GB": (Board.IGCSE_CIE, Board.STATE_BOARD),              # United Kingdom
    "FR": (Board.BAC_FR, Board.STATE_BOARD),                 # France
    "DE": (Board.ABITUR_DE, Board.STATE_BOARD),              # Germany
}


def _norm(country_code):
    """Normalise a country code to upper-case ISO-2 ('' when missing)."""
    return (country_code or "").strip().upper()[:2]


def allowed_board_values(country_code):
    """Ordered tuple of board VALUES appropriate for ``country_code``.

    Enum order is preserved for a stable UI. Unknown/empty country -> the full
    list (fail-open).
    """
    all_values = [value for value, _label in Board.choices]
    national = COUNTRY_BOARDS.get(_norm(country_code))
    if not national:
        return tuple(all_values)
    allowed = {str(v) for v in national} | {str(v) for v in INTERNATIONAL_BOARDS}
    return tuple(v for v in all_values if v in allowed)


def allowed_board_choices(country_code):
    """``[(value, label), ...]`` filtered to ``country_code`` for a form/select."""
    allowed = set(allowed_board_values(country_code))
    return [(value, label) for value, label in Board.choices if value in allowed]


def is_board_available_for_country(board_value, country_code):
    """True when ``board_value`` is appropriate for ``country_code``."""
    return str(board_value) in set(allowed_board_values(country_code))
