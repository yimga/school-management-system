"""Enforcement for the blueprint composition model.

The contract has always *declared* a composition model — ``composition_role``
(``base`` / ``regional_overlay`` / ``specialty_overlay`` / ``offline_overlay`` /
``operator_network``) plus a curated, symmetric ``compatible_blueprints``
adjacency list — and nothing read it at install time. Two bases could both be
applied to the same school, each carrying its own ``billing_defaults.plan`` and
``offline_defaults.mode``, so the second apply silently overwrote the first
school's operating model with an empty ``conflicts`` list and a full-marks
"Conflict-free" readiness score.

Severity is deliberately split, because the two cases carry different evidence:

* **base + base is a conflict and blocks.** A school has exactly one operating
  model; two of them is contradictory by construction, not a matter of taste.
  The way out is to roll the installed one back, which is a supported operation
  and clears the block.
* **an undeclared overlay pairing warns and does not block.** A missing entry in
  ``compatible_blueprints`` is at least as likely to be incomplete curation as a
  real incompatibility (a bilingual boarding school is a perfectly ordinary
  school, yet neither contract lists the other today). Blocking on that evidence
  would invent a rule the data does not support, so it informs instead.

This module is the single place both readings live, so the preview surface, the
dependency graph, and the apply engine cannot drift apart.
"""

from __future__ import annotations

from typing import Any

BASE_ROLE = "base"

CONFLICT_INCOMPATIBLE_BASE = "incompatible_base_blueprint"


def installed_blueprint_keys(school) -> list[str]:
    """Distinct blueprint keys currently APPLIED to this school."""
    if school is None:
        return []
    from apps.platform_runtime.models import BlueprintInstallation

    return sorted(
        set(
            BlueprintInstallation.objects.filter(
                school=school,
                status=BlueprintInstallation.Status.APPLIED,
            ).values_list("blueprint_key", flat=True)
        )
    )


def _declared_compatible(candidate, other) -> bool:
    """True when either contract declares the pairing, or neither declares any.

    An empty ``compatible_blueprints`` means "no composition constraints stated"
    (``multi-campus-network`` is the case in the catalog today), not "incompatible
    with everything" — reading it the other way would manufacture warnings from
    absent data.
    """
    if not candidate.compatible_blueprints and not other.compatible_blueprints:
        return True
    return (
        other.key in candidate.compatible_blueprints
        or candidate.key in other.compatible_blueprints
    )


def composition_findings(blueprint, *, school) -> dict[str, list[Any]]:
    """Blocking ``conflicts`` and non-blocking ``warnings`` for one candidate.

    Re-applying the *same* blueprint is never a composition finding — that path is
    idempotent and is handled by the apply engine's duplicate guard.
    """
    conflicts: list[dict[str, str]] = []
    warnings: list[str] = []

    installed = [key for key in installed_blueprint_keys(school) if key != blueprint.key]
    if not installed:
        return {"conflicts": conflicts, "warnings": warnings}

    from apps.platform_runtime.blueprint_contract import get_blueprint_or_raise

    for key in installed:
        try:
            other = get_blueprint_or_raise(key)
        except (KeyError, ValueError):
            # An installation naming a retired blueprint must not break the
            # preview of a healthy one.
            continue

        if blueprint.composition_role == BASE_ROLE and other.composition_role == BASE_ROLE:
            conflicts.append(
                {
                    "code": CONFLICT_INCOMPATIBLE_BASE,
                    "target": key,
                    "message": (
                        f"{other.name} ({key}) is already this school's operating model. "
                        f"Roll back {key} before applying {blueprint.key}."
                    ),
                }
            )
            continue

        if not _declared_compatible(blueprint, other):
            warnings.append(
                f"{blueprint.key} is not declared compatible with the installed "
                f"{key}; review overlay interactions before applying."
            )

    return {"conflicts": conflicts, "warnings": warnings}


def composition_conflicts(blueprint, *, school) -> list[dict[str, str]]:
    """Blocking conflicts only — the shape the dependency graph returns."""
    return composition_findings(blueprint, school=school)["conflicts"]
