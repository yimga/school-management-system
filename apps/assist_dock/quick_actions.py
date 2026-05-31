"""v4.00.91 Wave B — page-aware quick actions for the assist dock.

A quick action is a one-click shortcut surfaced inside the dock for the
current page. It's lighter than a chip (no panel) and can be page-bound
(e.g. ``/finance/invoices/`` → "Reconcile", "Generate statement"); other
apps register actions with a list of path prefixes / surfaces it should
appear on.

This module is intentionally additive — the existing command-bar registry
is its own SOT. Quick actions surface a curated subset in the dock chrome
itself so the operator doesn't have to open ⌘K for the obvious next step.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuickAction:
    id: str
    label: str
    icon: str                                       # Bootstrap Icon class
    href: str = ""                                  # ABS URL or path
    url_name: str = ""                              # Django URL name (preferred)
    path_prefixes: tuple[str, ...] = field(default_factory=tuple)
    surfaces: frozenset[str] = field(default_factory=frozenset)
    roles: frozenset[str] = field(default_factory=lambda: frozenset({"*"}))
    description: str = ""
    order: int = 100
    requires_feature: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("QuickAction.id must be a non-empty string")
        if not self.href and not self.url_name:
            raise ValueError(
                f"QuickAction {self.id!r}: must declare href OR url_name"
            )


_ACTIONS: dict[str, QuickAction] = {}


def register_quick_action(action: QuickAction) -> QuickAction:
    if not isinstance(action, QuickAction):
        raise TypeError("register_quick_action requires a QuickAction")
    _ACTIONS[action.id] = action
    return action


def unregister_quick_action(action_id: str) -> bool:
    return _ACTIONS.pop(action_id, None) is not None


def all_actions() -> list[QuickAction]:
    return list(_ACTIONS.values())


def reset_actions_for_tests() -> None:
    _ACTIONS.clear()


def _path_matches(action: QuickAction, page_path: str) -> bool:
    if not action.path_prefixes:
        return True
    return any(page_path.startswith(p) for p in action.path_prefixes)


def _surface_matches(action: QuickAction, surface: str) -> bool:
    if not action.surfaces:
        return True
    return "*" in action.surfaces or surface in action.surfaces


def _role_matches(action: QuickAction, role: str) -> bool:
    if "*" in action.roles:
        return True
    return role in action.roles


def actions_for(*, surface: str, role: str, page_path: str = "", limit: int = 6) -> list[QuickAction]:
    """Return ordered visible quick actions, capped at ``limit``."""
    surface = (surface or "*").strip() or "*"
    role = (role or "*").strip() or "*"
    out: list[QuickAction] = []
    for action in _ACTIONS.values():
        if not _surface_matches(action, surface):
            continue
        if not _role_matches(action, role):
            continue
        if not _path_matches(action, page_path):
            continue
        out.append(action)
    out.sort(key=lambda a: (a.order, a.id))
    return out[: max(0, int(limit))]


def resolve_href(action: QuickAction) -> str:
    """Resolve url_name (if set) via Django reverse(); fall back to href."""
    if action.url_name:
        try:
            from django.urls import reverse, NoReverseMatch

            try:
                return reverse(action.url_name)
            except NoReverseMatch:
                logger.debug(
                    "quick action %s url_name=%s did not resolve", action.id, action.url_name
                )
        except (ImportError, RuntimeError):
            pass
    return action.href or ""


def action_as_jsonable(action: QuickAction) -> dict:
    return {
        "id": action.id,
        "label": str(action.label),
        "icon": action.icon,
        "href": resolve_href(action),
        "description": str(action.description),
        "order": action.order,
    }


def actions_as_jsonable(actions: Iterable[QuickAction]) -> list[dict]:
    return [action_as_jsonable(a) for a in actions]


__all__ = [
    "QuickAction",
    "register_quick_action",
    "unregister_quick_action",
    "all_actions",
    "reset_actions_for_tests",
    "actions_for",
    "resolve_href",
    "action_as_jsonable",
    "actions_as_jsonable",
]
