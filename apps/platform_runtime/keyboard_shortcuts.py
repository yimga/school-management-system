"""Platform-wide keyboard shortcut Single Source of Truth (SOT).

Aggregates shortcuts from three layers:

1. **Global platform shortcuts** — chords that work on every page across every
   shell (portal / control plane / admin / marketing). Defined here.
2. **React luxWorkspace tier shortcuts** — chords bound to a specific
   spatial-personality tier (FINANCIAL_LEDGER / ACADEMIC_MATRIX / OPERATOR_SHELL).
   Read from `src/lib/luxWorkspace/registry.json` so the React side stays SOT
   for tier-bound chords.
3. **Surface-specific shortcuts** — chords scoped to one URL prefix
   (e.g. gradebook ⌘+S = save row). Surfaces register via `register_surface()`.

Public API:
- `iter_all_shortcuts()` → flat list of every chord on the platform
- `detect_conflicts()` → list of (chord, [bindings]) where the same chord is bound
  to different actions in different scopes
- `cheatsheet_payload()` → JSON-serializable payload for the `Cmd+/` help overlay
- `build_django_context()` → context-processor helper

This module is import-safe — no Django at import time — so vanilla scripts and
CI scanners can use it without standing up the framework.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
LUX_REGISTRY_PATH = REPO_ROOT / "src" / "lib" / "luxWorkspace" / "registry.json"


@dataclass(frozen=True)
class Shortcut:
    chord: str
    action: str
    label: str
    scope: str  # "global" | "tier:<TIER>" | "surface:<URL_PREFIX>"
    source: str  # file path or "platform-sot"


_GLOBAL_SHORTCUTS: tuple[Shortcut, ...] = (
    Shortcut(
        chord="Mod+k",
        action="OPEN_COMMAND_CONSOLE",
        label="Open command palette",
        scope="global",
        source="src/lib/luxWorkspace/registry.json",
    ),
    Shortcut(
        chord="Mod+/",
        action="OPEN_KEYBOARD_HELP",
        label="Show keyboard shortcuts",
        scope="global",
        source="src/lib/luxWorkspace/registry.json",
    ),
    Shortcut(
        chord="Escape",
        action="CLOSE_TOP_OVERLAY",
        label="Close current overlay",
        scope="global",
        source="src/lib/luxWorkspace/registry.json",
    ),
    Shortcut(
        chord="g h",
        action="NAVIGATE_HOME",
        label="Go to dashboard home",
        scope="global",
        source="platform-sot",
    ),
    Shortcut(
        chord="g s",
        action="NAVIGATE_SEARCH",
        label="Go to search",
        scope="global",
        source="platform-sot",
    ),
    Shortcut(
        chord="Shift+?",
        action="OPEN_KEYBOARD_HELP",
        label="Show keyboard shortcuts (alt)",
        scope="global",
        source="platform-sot",
    ),
)


_SURFACE_REGISTRY: dict[str, list[Shortcut]] = defaultdict(list)


def register_surface(url_prefix: str, shortcuts: Iterable[Mapping[str, str]]) -> None:
    """Register surface-scoped shortcuts.

    Surfaces register via this entrypoint at app-ready time so the SOT stays
    additive and stale entries get GC'd on import-cycle change. Idempotent.
    """
    scope = f"surface:{url_prefix}"
    out = []
    for raw in shortcuts:
        out.append(
            Shortcut(
                chord=raw["chord"],
                action=raw["action"],
                label=raw["label"],
                scope=scope,
                source=raw.get("source", "surface-registration"),
            )
        )
    _SURFACE_REGISTRY[url_prefix] = out


def _load_lux_tier_shortcuts() -> list[Shortcut]:
    if not LUX_REGISTRY_PATH.exists():
        return []
    try:
        data = json.loads(LUX_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out: list[Shortcut] = []
    tiers = data.get("tiers") or {}
    for tier_name, tier_def in tiers.items():
        bus = tier_def.get("keyboard_shortcuts_bus") or {}
        for chord, action in bus.items():
            out.append(
                Shortcut(
                    chord=chord,
                    action=action,
                    label=_humanize_action(action),
                    scope=f"tier:{tier_name}",
                    source="src/lib/luxWorkspace/registry.json",
                )
            )
    return out


def _humanize_action(action: str) -> str:
    return action.replace("_", " ").title()


def iter_all_shortcuts() -> list[Shortcut]:
    """Return every registered shortcut across all scopes."""
    out: list[Shortcut] = list(_GLOBAL_SHORTCUTS)
    out.extend(_load_lux_tier_shortcuts())
    for surface_shortcuts in _SURFACE_REGISTRY.values():
        out.extend(surface_shortcuts)
    return out


def detect_conflicts() -> list[tuple[str, list[Shortcut]]]:
    """Find chords bound to >1 distinct action across global scope.

    Tier-scoped and surface-scoped chords are allowed to reuse the same chord
    as long as their scopes don't overlap — the React kernel only dispatches
    the chord matching the active tier. Conflicts within the same scope
    (or between two different global bindings) are real bugs.
    """
    by_chord: dict[tuple[str, str], list[Shortcut]] = defaultdict(list)
    for s in iter_all_shortcuts():
        by_chord[(s.chord, s.scope)].append(s)

    conflicts: list[tuple[str, list[Shortcut]]] = []
    for (chord, scope), bindings in by_chord.items():
        distinct_actions = {b.action for b in bindings}
        if len(distinct_actions) > 1:
            conflicts.append((f"{chord}@{scope}", bindings))
    return conflicts


def cheatsheet_payload() -> dict:
    """JSON-serializable payload for the keyboard-help overlay."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for s in iter_all_shortcuts():
        grouped[s.scope].append(
            {
                "chord": s.chord,
                "action": s.action,
                "label": s.label,
            }
        )
    return {"scopes": dict(grouped)}


def build_django_context(request=None) -> dict:
    """Django context-processor helper for shells that want the cheat-sheet inline."""
    return {
        "platform_keyboard_shortcuts": cheatsheet_payload(),
    }
