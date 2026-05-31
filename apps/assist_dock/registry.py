"""v4.00.91 — assist dock SOT registry.

Every chip in the right-edge floating rail is one ``AssistDockSlot`` row.
Add a chip by calling ``register_slot(...)`` from any AppConfig.ready hook.

The registry is process-local + idempotent (re-registering the same id
overwrites the existing slot). No DB; no migrations — slots are code.

Filtering contract: ``get_slots_for(surface=..., role=...)`` returns the
visible-ordered list. ``"*"`` in ``surfaces`` or ``roles`` means "any".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Iterable

logger = logging.getLogger(__name__)


# Canonical surface identifiers — match data-surface emitted by each shell.
SURFACE_PORTAL = "portal"      # tenant portal_base.html
SURFACE_MANAGER = "manager"    # control_plane_skeleton.html (manager host)
SURFACE_ADMIN = "admin"        # admin/base_site.html (Django admin)
SURFACE_ANY = "*"

ALL_SURFACES = frozenset({SURFACE_PORTAL, SURFACE_MANAGER, SURFACE_ADMIN})

# Slot source kinds:
#  - "dom-adopt"   JS adopts an existing source node by CSS selector
#                  (back-compat for the 6 v1 chips; the widget still lives
#                  in its original template, we just declare it via registry)
#  - "registry"    server-rendered button/link from registry fields alone
#                  (Wave A+); panel may be URL-name or template path
#  - "external"    link that opens an external URL (rare; mostly for help)
SOURCE_DOM_ADOPT = "dom-adopt"
SOURCE_REGISTRY = "registry"
SOURCE_EXTERNAL = "external"
VALID_SOURCES = frozenset({SOURCE_DOM_ADOPT, SOURCE_REGISTRY, SOURCE_EXTERNAL})


@dataclass(frozen=True)
class AssistDockSlot:
    """One chip in the assist dock.

    Required: ``id``, ``label``, ``icon``.
    Sane defaults for everything else so callers stay terse.

    Wave A: ``badge_source`` / ``shortcut`` / ``panel_url_name`` are
    declared but only read by the JS in Wave B+.
    """

    id: str
    label: str
    icon: str                                  # Bootstrap Icon class, e.g. "bi-stars"
    surfaces: frozenset[str] = field(default_factory=lambda: frozenset({SURFACE_ANY}))
    roles: frozenset[str] = field(default_factory=lambda: frozenset({"*"}))
    source: str = SOURCE_REGISTRY
    adopt_selector: str = ""                    # for source="dom-adopt"
    panel_url_name: str = ""                    # for source="registry" w/ URL panel
    panel_template: str = ""                    # for source="registry" w/ template panel
    href: str = ""                              # for source="external"
    badge_source: str = ""                      # Wave B — URL name returning {count, dot, level}
    shortcut: str = ""                          # display-only label e.g. "g a"
    aria_keyshortcuts: str = ""                 # WAI-ARIA shortcut declaration
    pinned_default: bool = False                # primary row vs "more" tray
    order: int = 100                            # sort order, ascending
    requires_feature: str = ""                  # optional feature flag gate
    description: str = ""                       # tooltip / a11y description

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ValueError("AssistDockSlot.id must be a non-empty string")
        if self.source not in VALID_SOURCES:
            raise ValueError(
                f"AssistDockSlot.source={self.source!r} not in {sorted(VALID_SOURCES)}"
            )
        if self.source == SOURCE_DOM_ADOPT and not self.adopt_selector:
            raise ValueError(
                f"slot {self.id!r}: source='dom-adopt' requires adopt_selector"
            )
        if self.source == SOURCE_EXTERNAL and not self.href:
            raise ValueError(f"slot {self.id!r}: source='external' requires href")


_REGISTRY: dict[str, AssistDockSlot] = {}


def register_slot(slot: AssistDockSlot) -> AssistDockSlot:
    """Register / replace a slot. Returns the registered slot.

    Idempotent: re-registering the same id overwrites the previous entry,
    so re-running ``AppConfig.ready`` (e.g. during tests) is safe.
    """
    if not isinstance(slot, AssistDockSlot):
        raise TypeError("register_slot requires an AssistDockSlot instance")
    _REGISTRY[slot.id] = slot
    return slot


def unregister_slot(slot_id: str) -> bool:
    """Remove a slot. Returns True if it was present, False otherwise."""
    return _REGISTRY.pop(slot_id, None) is not None


def get_slot(slot_id: str) -> AssistDockSlot | None:
    return _REGISTRY.get(slot_id)


def all_slots() -> list[AssistDockSlot]:
    """Snapshot of every registered slot, unsorted."""
    return list(_REGISTRY.values())


def _surface_matches(slot: AssistDockSlot, surface: str) -> bool:
    # Bilateral wildcard: caller asking "*" OR slot declaring "*" → match.
    if surface == SURFACE_ANY or SURFACE_ANY in slot.surfaces:
        return True
    return surface in slot.surfaces


def _role_matches(slot: AssistDockSlot, role: str) -> bool:
    if role == "*" or "*" in slot.roles:
        return True
    return role in slot.roles


def get_slots_for(
    *,
    surface: str,
    role: str = "*",
    include_hidden: bool = False,
) -> list[AssistDockSlot]:
    """Return registry slots visible to (surface, role), sorted by order.

    ``include_hidden=True`` returns disabled / feature-flag-gated slots too;
    callers that want a strict visible list should leave it False.

    Surfaces / roles are matched case-sensitively against the slot's frozenset.
    Use ``"*"`` to short-circuit either filter.
    """
    surface = (surface or "").strip() or SURFACE_ANY
    role = (role or "*").strip() or "*"
    out: list[AssistDockSlot] = []
    for slot in _REGISTRY.values():
        if not _surface_matches(slot, surface):
            continue
        if not _role_matches(slot, role):
            continue
        if slot.requires_feature and not include_hidden:
            # Feature flag resolution lives in the context processor so the
            # registry stays pure — including for tests.
            continue
        out.append(slot)
    out.sort(key=lambda s: (s.order, s.id))
    return out


def reset_registry_for_tests() -> None:
    """Clear the registry. Tests only — production code should never call this."""
    _REGISTRY.clear()


def replace_slot(slot_id: str, **changes) -> AssistDockSlot | None:
    """Replace fields on a registered slot. Returns the new slot or None.

    Convenience for downstream apps that want to tweak a default chip
    (e.g. change its ``order`` or attach a ``badge_source``) without
    re-declaring every field.
    """
    existing = _REGISTRY.get(slot_id)
    if existing is None:
        return None
    new_slot = replace(existing, **changes)
    _REGISTRY[slot_id] = new_slot
    return new_slot


def slot_as_jsonable(slot: AssistDockSlot) -> dict:
    """Serialize a slot for the JSON island the JS hydrates from.

    frozensets are converted to sorted lists so the JSON output is
    deterministic across requests / cache layers.
    """
    return {
        "id": slot.id,
        "label": str(slot.label),
        "icon": slot.icon,
        "surfaces": sorted(slot.surfaces),
        "roles": sorted(slot.roles),
        "source": slot.source,
        "adopt_selector": slot.adopt_selector,
        "panel_url_name": slot.panel_url_name,
        "panel_template": slot.panel_template,
        "href": slot.href,
        "badge_source": slot.badge_source,
        "shortcut": slot.shortcut,
        "aria_keyshortcuts": slot.aria_keyshortcuts,
        "pinned_default": slot.pinned_default,
        "order": slot.order,
        "description": str(slot.description),
    }


def slots_as_jsonable(slots: Iterable[AssistDockSlot]) -> list[dict]:
    return [slot_as_jsonable(s) for s in slots]


__all__ = [
    "AssistDockSlot",
    "SURFACE_PORTAL",
    "SURFACE_MANAGER",
    "SURFACE_ADMIN",
    "SURFACE_ANY",
    "ALL_SURFACES",
    "SOURCE_DOM_ADOPT",
    "SOURCE_REGISTRY",
    "SOURCE_EXTERNAL",
    "VALID_SOURCES",
    "register_slot",
    "unregister_slot",
    "get_slot",
    "all_slots",
    "get_slots_for",
    "reset_registry_for_tests",
    "replace_slot",
    "slot_as_jsonable",
    "slots_as_jsonable",
]
