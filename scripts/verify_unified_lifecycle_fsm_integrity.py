#!/usr/bin/env python3
"""Structural-integrity gate for the unified tenant-lifecycle FSM.

WHY THIS EXISTS
---------------
``apps/lifecycle/unified_lifecycle.py`` is the single resolver/write-facade for
the tenant lifecycle (draft -> provisioning -> activating -> live -> wind_down ->
closed -> purged). Its correctness rests on three hand-maintained tables:

  * ``ALL_UNIFIED_STATES``           - the canonical state vocabulary.
  * ``_ALLOWED_TRANSITIONS``         - the adjacency map the validator enforces.
  * ``UNIFIED_STATE_TO_SPINE_STAGE`` - which append-only spine stage each state
                                        records when entered.

Nothing protected those tables from drift. The validator itself was, per the
in-file comment, "previously dead code" until it was finally wired into the write
path — so the FSM's integrity has never been load-bearing in CI. Concretely, a
future edit could:

  * add a state to ``ALL_UNIFIED_STATES`` but forget ``_ALLOWED_TRANSITIONS`` ->
    ``validate_unified_transition`` returns False for EVERY transition out of it
    (``.get(state, frozenset())``), silently bricking that state with no error;
  * point a transition at a typo'd / removed target state -> a transition that
    can never validate;
  * forget the spine-stage mapping for a new non-draft state -> entering it
    records NO breadcrumb on the append-only timeline (Tenant 360 goes blind);
  * leave a state unreachable from ``draft`` -> a dead island no tenant can enter.

This gate locks all four. It is a structural assertion on module-level data
(no DB), so it is cheap and deterministic.

Django-aware (the spine-stage map values are ``SchoolLifecycleStage.Stage``
members), so it runs in ``ci.yml::django-tests`` alongside the other
model-introspecting gates. Pure pass/fail (exit 0/1), zero-tolerance — no
finding baseline, like ``verify_runtime_defaults_model_parity.py``.

Run: ``python scripts/verify_unified_lifecycle_fsm_integrity.py``
Exit: 0 on a coherent FSM, 1 on any structural drift.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The single state that legitimately has no spine-stage mapping: a tenant that
# is still a draft has not landed a SchoolLifecycleStage row yet.
_SPINE_EXEMPT_STATES: frozenset[str] = frozenset({"draft"})


def _collect():
    import django

    # Make the repo root importable when run standalone (python scripts/<this>.py
    # puts scripts/ on sys.path[0], not the repo root).
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    from apps.lifecycle.models import SchoolLifecycleStage
    from apps.lifecycle import unified_lifecycle as ul

    valid_stage_values = {choice[0] for choice in SchoolLifecycleStage.Stage.choices}
    return ul, valid_stage_values


def _reachable_from(start: str, transitions: dict) -> set[str]:
    """BFS over the adjacency map from ``start`` (inclusive)."""
    seen = {start}
    frontier = [start]
    while frontier:
        node = frontier.pop()
        for nxt in transitions.get(node, frozenset()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return seen


def find_errors(ul, valid_stage_values: set[str]) -> list[str]:
    errors: list[str] = []

    states = set(ul.ALL_UNIFIED_STATES)
    transitions = ul._ALLOWED_TRANSITIONS
    spine_map = ul.UNIFIED_STATE_TO_SPINE_STAGE

    # I1: every declared state must have an outbound-transition entry (even if
    # empty), and no transition entry may name an unknown state.
    missing_keys = sorted(states - set(transitions.keys()))
    for s in missing_keys:
        errors.append(
            f"state {s!r} is in ALL_UNIFIED_STATES but has NO _ALLOWED_TRANSITIONS "
            "entry -> every transition out of it silently fails (validator returns "
            "False). Add an explicit (possibly empty) frozenset."
        )
    extra_keys = sorted(set(transitions.keys()) - states)
    for s in extra_keys:
        errors.append(
            f"_ALLOWED_TRANSITIONS has key {s!r} that is not in ALL_UNIFIED_STATES "
            "(stale/typo'd state)."
        )

    # I2: every transition TARGET must be a real state.
    for src, targets in transitions.items():
        for tgt in sorted(set(targets) - states):
            errors.append(
                f"_ALLOWED_TRANSITIONS[{src!r}] points at {tgt!r} which is not a "
                "declared unified state (typo / removed target)."
            )

    # I3: the terminal state must truly be terminal.
    purged = getattr(ul, "STATE_PURGED", "purged")
    if transitions.get(purged) != frozenset():
        errors.append(
            f"terminal state {purged!r} must have an EMPTY transition set; found "
            f"{sorted(transitions.get(purged, frozenset()))!r}."
        )

    # I4: spine-stage map keys are real states; values are real spine stages.
    for s in sorted(set(spine_map.keys()) - states):
        errors.append(
            f"UNIFIED_STATE_TO_SPINE_STAGE has key {s!r} that is not a declared "
            "unified state."
        )
    for s, stage in spine_map.items():
        if stage not in valid_stage_values:
            errors.append(
                f"UNIFIED_STATE_TO_SPINE_STAGE[{s!r}] = {stage!r} is not a valid "
                "SchoolLifecycleStage.Stage choice."
            )

    # I5: every non-exempt state must map to a spine stage, so entering it leaves
    # an audit breadcrumb on the timeline.
    for s in sorted(states - set(spine_map.keys()) - _SPINE_EXEMPT_STATES):
        errors.append(
            f"state {s!r} has no UNIFIED_STATE_TO_SPINE_STAGE mapping -> a unified "
            "transition into it records nothing on the append-only spine. Add a "
            "mapping, or add the state to _SPINE_EXEMPT_STATES in this gate with a "
            "reason."
        )

    # I6: every state must be reachable from draft (no dead islands).
    draft = getattr(ul, "STATE_DRAFT", "draft")
    if draft in states:
        reachable = _reachable_from(draft, transitions)
        for s in sorted(states - reachable):
            errors.append(
                f"state {s!r} is unreachable from {draft!r} via _ALLOWED_TRANSITIONS "
                "(dead island — no tenant can ever enter it)."
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    try:
        ul, valid_stage_values = _collect()
    except Exception as exc:  # noqa: BLE001 — bootstrap failure is a gate failure
        print("verify_unified_lifecycle_fsm_integrity: FAILED", file=sys.stderr)
        print(f"  - could not import unified_lifecycle: {exc}", file=sys.stderr)
        return 1

    errors = find_errors(ul, valid_stage_values)
    if errors:
        print("verify_unified_lifecycle_fsm_integrity: FAILED", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        "verify_unified_lifecycle_fsm_integrity: PASS "
        f"({len(ul.ALL_UNIFIED_STATES)} states, "
        f"{sum(len(v) for v in ul._ALLOWED_TRANSITIONS.values())} transitions, "
        f"{len(ul.UNIFIED_STATE_TO_SPINE_STAGE)} spine mappings — all coherent)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
