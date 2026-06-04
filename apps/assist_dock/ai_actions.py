"""v4.00.94 Wave D — page-aware AI action vocabulary.

Each action is a structured prompt template the dock can fire against the
AI gateway. ``invoke_action(...)`` routes through ``services.ai_helpers``
(the canonical entry-point per CLAUDE.md; direct ``services.ai_gateway``
import is fenced by the ``architectural-boundaries`` gate).

Built-in actions:

  * ``summarize`` — "What is this page about, in 3 bullet points?"
  * ``explain``   — "Explain this element / column / metric to a teacher."
  * ``draft``     — "Draft an email / announcement from this short brief."
  * ``translate`` — "Translate this text to the operator's locale."

Other apps register additional actions by calling ``register_action(...)``
from their own AppConfig.ready hook; the JS dispatch is generic over the
action id, so a new action becomes a one-line registry entry.

The action's prompt template is rendered server-side with simple ``str.format``
substitutions — there is no execution / eval / template engine, so a
hostile ``page_excerpt`` cannot escape the prompt boundary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)


# Task type — passed through to services.ai_helpers as a string so we never
# import services.ai_gateway directly (architectural boundary).
DEFAULT_TASK_TYPE = "admin_copilot"

# Cap rendered prompt length so a runaway page_excerpt can't blow past the
# gateway's model context. The gateway will truncate further if needed.
PROMPT_MAX_CHARS = 4000  # magic-number-allow: ai-message-char-cap

# Cap response chars surfaced back to the JS — never echo a full PII dump.
RESPONSE_MAX_CHARS = 2000


@dataclass(frozen=True)
class AIAction:
    """A registered page-aware AI action.

    ``prompt_template`` may contain ``{page_path}`` / ``{page_excerpt}`` /
    ``{user_query}`` / ``{role}`` substitutions. Unknown substitutions
    raise a KeyError at render time — caller's responsibility.
    """

    id: str
    label: str
    icon: str = "bi-stars"
    description: str = ""
    prompt_template: str = ""
    task_type: str = DEFAULT_TASK_TYPE
    response_schema: str = ""
    surfaces: frozenset[str] = field(default_factory=frozenset)   # empty = all
    roles: frozenset[str] = field(default_factory=lambda: frozenset({"*"}))
    requires_feature: str = ""
    order: int = 100

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("AIAction.id must be a non-empty string")
        if not self.prompt_template:
            raise ValueError(f"AIAction {self.id!r}: prompt_template required")


_ACTIONS: dict[str, AIAction] = {}


def register_action(action: AIAction) -> AIAction:
    if not isinstance(action, AIAction):
        raise TypeError("register_action requires an AIAction")
    _ACTIONS[action.id] = action
    return action


def unregister_action(action_id: str) -> bool:
    return _ACTIONS.pop(action_id, None) is not None


def get_action(action_id: str) -> AIAction | None:
    return _ACTIONS.get(action_id)


def all_actions() -> list[AIAction]:
    return list(_ACTIONS.values())


def reset_actions_for_tests() -> None:
    _ACTIONS.clear()


def render_prompt(action: AIAction, ctx: dict) -> str:
    """Render the action's template against ``ctx``; cap at PROMPT_MAX_CHARS."""
    safe_ctx = {
        "page_path": str(ctx.get("page_path") or "")[:512],
        "page_excerpt": str(ctx.get("page_excerpt") or "")[:2000],
        "user_query": str(ctx.get("user_query") or "")[:512],
        "role": str(ctx.get("role") or ""),
        "surface": str(ctx.get("surface") or ""),
    }
    try:
        prompt = action.prompt_template.format(**safe_ctx)
    except (KeyError, IndexError) as exc:
        logger.debug("ai action %s prompt render failed: %s", action.id, exc)
        prompt = action.prompt_template
    return prompt[:PROMPT_MAX_CHARS]


def invoke_action(
    *,
    action_id: str,
    request,
    page_path: str = "",
    page_excerpt: str = "",
    user_query: str = "",
) -> dict:
    """Run a registered action through ``services.ai_helpers``.

    Returns a dict ``{ok, text, action_id, task_type, error}`` so the
    caller (JS bridge) gets a deterministic envelope regardless of
    success / failure. Never raises into the view layer.
    """
    action = _ACTIONS.get(action_id)
    if action is None:
        return {
            "ok": False,
            "text": "",
            "action_id": action_id,
            "error": "unknown_action",
        }
    role = ""
    try:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            for attr in ("active_role", "primary_role", "role"):
                value = getattr(user, attr, None)
                if value:
                    role = str(value)
                    break
    except (AttributeError, RuntimeError):
        role = ""
    prompt = render_prompt(
        action,
        {
            "page_path": page_path,
            "page_excerpt": page_excerpt,
            "user_query": user_query,
            "role": role,
            "surface": "",
        },
    )
    try:
        from services.ai_helpers import invoke_with_request
    except (ImportError, RuntimeError) as exc:
        logger.debug("ai_helpers import failed: %s", exc)
        return {
            "ok": False,
            "text": "",
            "action_id": action_id,
            "task_type": action.task_type,
            "error": "gateway_unavailable",
        }
    try:
        result = invoke_with_request(
            task_type=action.task_type,
            prompt=prompt,
            request=request,
            user_query=user_query or action.label,
            response_schema=action.response_schema or None,
            require_available=False,
        )
    except Exception as exc:  # noqa: BLE001 — gateway can raise broad classes
        logger.debug("ai action %s invoke failed: %s", action_id, exc)
        return {
            "ok": False,
            "text": "",
            "action_id": action_id,
            "task_type": action.task_type,
            "error": "gateway_error",
        }
    if result is None:
        return {
            "ok": False,
            "text": "",
            "action_id": action_id,
            "task_type": action.task_type,
            "error": "ai_disabled_by_policy",
        }
    text, metadata = result if isinstance(result, tuple) else (result, {})
    rendered = (str(text) if text is not None else "")[:RESPONSE_MAX_CHARS]
    return {
        "ok": True,
        "text": rendered,
        "action_id": action_id,
        "task_type": action.task_type,
        "tier": (metadata or {}).get("tier", "unknown"),
    }


def action_as_jsonable(action: AIAction) -> dict:
    return {
        "id": action.id,
        "label": str(action.label),
        "icon": action.icon,
        "description": str(action.description),
        "order": action.order,
    }


def actions_as_jsonable(actions: Iterable[AIAction]) -> list[dict]:
    return [action_as_jsonable(a) for a in actions]


__all__ = [
    "DEFAULT_TASK_TYPE",
    "PROMPT_MAX_CHARS",
    "RESPONSE_MAX_CHARS",
    "AIAction",
    "register_action",
    "unregister_action",
    "get_action",
    "all_actions",
    "reset_actions_for_tests",
    "render_prompt",
    "invoke_action",
    "action_as_jsonable",
    "actions_as_jsonable",
]
