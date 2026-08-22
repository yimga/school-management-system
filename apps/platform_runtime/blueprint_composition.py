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

# Installations in these states still occupy the tenant's operating-model slot.
_ACTIVE_INSTALL_STATUSES: frozenset[str] = frozenset(
    {
        "applied",
        "partially_applied",
    }
)


def _installation_sort_key(row) -> tuple:
    """Order installations newest-first within a blueprint_key."""
    stamp = row.applied_at or row.created_at
    return (stamp, row.pk)


def _latest_installation_by_key(school) -> dict[str, object]:
    """Most recent BlueprintInstallation row per blueprint_key for this school."""
    if school is None:
        return {}
    from apps.platform_runtime.models import BlueprintInstallation

    latest: dict[str, BlueprintInstallation] = {}
    rows = BlueprintInstallation.objects.filter(school=school).only(
        "pk",
        "blueprint_key",
        "status",
        "applied_at",
        "created_at",
    )
    for row in rows:
        prev = latest.get(row.blueprint_key)
        if prev is None or _installation_sort_key(row) > _installation_sort_key(prev):
            latest[row.blueprint_key] = row
    return latest


def effective_installed_blueprint_keys(school) -> list[str]:
    """Blueprint keys whose *latest* installation row is actively installed.

    A tenant can accumulate multiple installation rows for the same blueprint_key
    (version bumps use different idempotency keys). Rolling back only the newest
    row must not leave an older ``applied`` row blocking the next base blueprint.
    """
    latest = _latest_installation_by_key(school)
    return sorted(
        key
        for key, row in latest.items()
        if row.status in _ACTIVE_INSTALL_STATUSES
    )


def installed_blueprint_keys(school) -> list[str]:
    """Distinct blueprint keys currently installed on this school."""
    return effective_installed_blueprint_keys(school)


def reconcile_blueprint_marketplace_markers(school) -> list[str]:
    """Drop stale ``school.settings`` blueprint markers with no live installation."""
    if school is None:
        return []
    effective = set(effective_installed_blueprint_keys(school))
    settings = dict(getattr(school, "settings", None) or {})
    removed: list[str] = []
    changed = False
    for bucket in ("blueprint_marketplace", "local_first_blueprints"):
        markers = dict(settings.get(bucket) or {})
        for key in list(markers):
            if key not in effective:
                del markers[key]
                removed.append(key)
                changed = True
        if markers:
            settings[bucket] = markers
        elif bucket in settings:
            settings.pop(bucket, None)
            changed = True
    if changed:
        school.settings = settings
        school.save(update_fields=["settings"])
    return removed


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
