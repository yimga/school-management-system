"""v4.00.14 — subject→topic curriculum map for adaptive recommendations.

Closes the v4.00.13 follow-on opportunity: ``signals_adaptive.py`` fell back
to ``current_topic_key`` when remedial/follow_on/advanced keys were absent,
producing flat (non-actionable) recommendations. This module supplies the
curriculum graph.

A "subject" is the gradebook subject (math, english, physics, …). Each
subject carries an ordered list of topics; for any given topic the kernel
needs three siblings:

* ``remedial_topic_key`` — the topic the student should fall back to when
  recent scores are below the band threshold.
* ``follow_on_topic_key`` — the next topic in the curriculum for an
  on-track student.
* ``advanced_topic_key`` — an enrichment topic for students who have
  mastered the current level.

The map ships sensible defaults for common subjects. Schools can override
via ``School.settings["academics"]["curriculum_map"][<subject>]`` — same
shape as the in-memory map. The school override wins.

Pure-Python — no DB writes. Safe to import from signal handlers + tasks.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# Default curriculum graph
# ============================================================================

# Ordered topic chains per subject. Each entry's index in the list is its
# "level": index 0 is foundational, index N-1 is the most advanced ready-to-go
# topic. The kernel maps (current_topic, band) -> sibling topic via:
#
#   remedial    = chain[max(0, i-1)]
#   follow_on   = chain[min(len-1, i+1)]
#   advanced    = chain[min(len-1, i+2)]
#
# Curriculum chains are intentionally short — the kernel is a recommender, not
# a teacher. Schools layer their own chains via the override mechanism below.
_DEFAULT_CHAINS: dict[str, tuple[str, ...]] = {
    "math": (
        "math.arithmetic",
        "math.fractions",
        "math.algebra_intro",
        "math.linear_equations",
        "math.quadratic_equations",
        "math.functions",
        "math.precalculus",
        "math.calculus_intro",
    ),
    "english": (
        "english.phonics",
        "english.reading_comprehension",
        "english.grammar_basics",
        "english.essay_structure",
        "english.persuasive_writing",
        "english.literary_analysis",
        "english.rhetoric",
    ),
    "physics": (
        "physics.units_measurement",
        "physics.kinematics",
        "physics.dynamics",
        "physics.energy_work",
        "physics.waves_intro",
        "physics.electromagnetism_intro",
        "physics.modern_physics",
    ),
    "chemistry": (
        "chemistry.matter_states",
        "chemistry.atomic_structure",
        "chemistry.periodic_table",
        "chemistry.chemical_bonding",
        "chemistry.stoichiometry",
        "chemistry.acids_bases",
        "chemistry.organic_intro",
    ),
    "biology": (
        "biology.cell_basics",
        "biology.cell_division",
        "biology.genetics_intro",
        "biology.ecology",
        "biology.evolution",
        "biology.human_systems",
    ),
    "history": (
        "history.timelines_basics",
        "history.ancient_civilizations",
        "history.medieval_period",
        "history.early_modern",
        "history.world_wars",
        "history.contemporary",
    ),
    "geography": (
        "geography.map_skills",
        "geography.physical_features",
        "geography.climate_zones",
        "geography.human_geography",
        "geography.economic_geography",
    ),
    "computer_science": (
        "cs.computer_basics",
        "cs.intro_programming",
        "cs.control_flow",
        "cs.data_structures_intro",
        "cs.algorithms_intro",
        "cs.databases_intro",
    ),
}


def _normalize_subject(subject_key: str) -> str:
    """Coerce a raw subject identifier to one of the chain keys."""
    if not subject_key:
        return ""
    key = str(subject_key).strip().lower()
    # Allow `math.algebra_intro` → `math`, `english_lang` → `english`, etc.
    for chain_key in _DEFAULT_CHAINS:
        if key == chain_key or key.startswith(chain_key + ".") or key.startswith(chain_key + "_"):
            return chain_key
    return ""


def _resolve_chain(subject_key: str, *, school_overrides: dict[str, Any] | None) -> tuple[str, ...]:
    """Return the topic chain for ``subject_key``, preferring school overrides."""
    normalized = _normalize_subject(subject_key)
    if not normalized:
        return ()
    if isinstance(school_overrides, dict):
        override = school_overrides.get(normalized)
        if isinstance(override, (list, tuple)) and override:
            return tuple(str(t) for t in override if t)
    return _DEFAULT_CHAINS.get(normalized, ())


def _current_index(chain: tuple[str, ...], current_topic_key: str) -> int:
    """Return the position of ``current_topic_key`` in ``chain``, or 0 when unknown."""
    if not chain:
        return 0
    if not current_topic_key:
        return 0
    key = str(current_topic_key).strip()
    for index, topic in enumerate(chain):
        if topic == key:
            return index
    return 0


def resolve_topic_siblings(
    *,
    subject_key: str,
    current_topic_key: str,
    school_settings: dict[str, Any] | None = None,
) -> dict[str, str | None]:
    """Return ``{remedial, follow_on, advanced}`` topic keys for the kernel.

    School-level overrides at ``school.settings["academics"]["curriculum_map"]``
    take precedence over the shipped defaults. When the subject is unknown or
    the chain is empty, returns all-``None`` so the kernel falls back to
    ``current_topic_key`` (its existing no-curriculum behaviour).
    """
    overrides: dict[str, Any] | None = None
    if isinstance(school_settings, dict):
        ac = school_settings.get("academics") or {}
        if isinstance(ac, dict):
            cm = ac.get("curriculum_map")
            if isinstance(cm, dict):
                overrides = cm

    chain = _resolve_chain(subject_key, school_overrides=overrides)
    if not chain:
        return {"remedial": None, "follow_on": None, "advanced": None}

    index = _current_index(chain, current_topic_key)
    last = len(chain) - 1
    remedial = chain[max(0, index - 1)]
    follow_on = chain[min(last, index + 1)]
    advanced = chain[min(last, index + 2)]
    return {"remedial": remedial, "follow_on": follow_on, "advanced": advanced}


def list_supported_subjects() -> tuple[str, ...]:
    """Introspection helper for the operator-config UI."""
    return tuple(sorted(_DEFAULT_CHAINS.keys()))


def chain_for_subject(subject_key: str) -> tuple[str, ...]:
    """Read-only accessor for the default chain — surfaces in operator UI."""
    normalized = _normalize_subject(subject_key)
    return _DEFAULT_CHAINS.get(normalized, ())
