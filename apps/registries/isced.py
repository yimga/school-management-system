"""Pure UNESCO ISCED 2011 progression spine — no Django, no DB.

This module is the canonical, side-effect-free source of truth for the
International Standard Classification of Education (ISCED 2011) levels 0-8 and
their mapping onto the coarse ``EducationLevelRegistry.tier`` grammar. It is
imported by the DB-backed seed (``apps.registries.services``) and will later be
consulted by the M29 progression / year-rollover matrix — so it MUST stay
importable with zero Django app-loading side effects (no model imports, no
``django.setup`` dependency).

The tier code strings below are the load-bearing contract; they MUST equal the
values of ``EducationLevelRegistry.Tier`` (a contract test asserts this).
"""

from __future__ import annotations

# --- Tier codes -------------------------------------------------------------
# Keep in lock-step with ``apps.registries.models.EducationLevelRegistry.Tier``.
TIER_EARLY_CHILDHOOD = "EARLY_CHILDHOOD"
TIER_K12 = "K12"
TIER_TERTIARY = "TERTIARY"


# --- ISCED 2011 canonical levels -------------------------------------------
ISCED_MIN_LEVEL = 0
ISCED_MAX_LEVEL = 8

# UNESCO ISCED 2011 level -> canonical English name.
ISCED_LEVEL_NAMES: dict[int, str] = {
    0: "Early childhood",
    1: "Primary",
    2: "Lower secondary",
    3: "Upper secondary",
    4: "Post-secondary non-tertiary",
    5: "Short-cycle tertiary",
    6: "Bachelor",
    7: "Master",
    8: "Doctoral",
}

# Representative ISCED level for each of the 3 coarse registry codes, so the
# pre-existing coarse rows get a defensible ``isced_level`` on backfill.
#   PRIMARY   -> 1 (Primary)
#   SECONDARY -> 2 (Lower secondary is the representative; upper-secondary = 3)
#   TERTIARY  -> 6 (Bachelor is the representative tertiary entry point;
#                   short-cycle tertiary = 5, Master = 7, Doctoral = 8)
ISCED_SPAN_FOR_LEVEL_CODE: dict[str, int] = {
    "PRIMARY": 1,
    "SECONDARY": 2,
    "TERTIARY": 6,
}


def _validate_level(level: int) -> int:
    """Coerce/validate an ISCED level to an int in 0..8, else ``ValueError``."""
    try:
        value = int(level)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"ISCED level must be an integer, got {level!r}") from exc
    if not (ISCED_MIN_LEVEL <= value <= ISCED_MAX_LEVEL):
        raise ValueError(
            f"ISCED level {value} out of range "
            f"{ISCED_MIN_LEVEL}..{ISCED_MAX_LEVEL}"
        )
    return value


def isced_level_name(level: int) -> str:
    """Return the canonical ISCED 2011 name for ``level`` (0-8)."""
    return ISCED_LEVEL_NAMES[_validate_level(level)]


def next_isced_level(level: int) -> int | None:
    """Return the next ISCED level, or ``None`` at the top of the ladder.

    0->1->2->...->7->8, and 8->None. The M29 rollover matrix will consult this
    to decide the successor level when a cohort completes a stage.
    """
    value = _validate_level(level)
    if value >= ISCED_MAX_LEVEL:
        return None
    return value + 1


def tier_for_isced(level: int) -> str:
    """Map an ISCED level (0-8) onto the coarse tier grammar.

    0        -> EARLY_CHILDHOOD
    1, 2, 3  -> K12
    4        -> K12 (post-secondary non-tertiary sits on the K12/tertiary
                boundary; classified as K12 here because it is not yet a
                tertiary qualification — revisit if a distinct tier is needed)
    5, 6, 7, 8 -> TERTIARY
    """
    value = _validate_level(level)
    if value == 0:
        return TIER_EARLY_CHILDHOOD
    if value <= 4:  # 1, 2, 3, and the 4 boundary case
        return TIER_K12
    return TIER_TERTIARY
