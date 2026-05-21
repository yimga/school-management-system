"""AI copilot service — v3.57.0 (2026-05-21).

Powers the v3.56.0 manager `_ai_copilot_rail.html` partial that floats in
the 3rd grid column of `[data-rmc-shell-main="control-plane"]`. The rail
surfaces suggested operator actions, recent AI activity, and a Cmd/Ctrl+K
quick-prompt button.

This module is an **honest stub** in v3.57.0. The real copilot wiring goes
through `services.ai_helpers.invoke_with_request` per CLAUDE.md's preserve
list — this stub returns structured "no suggestions yet" defaults so the
partial renders without raising. When wave v3.58+ flips the real wiring
in `apps/observability/views.py`, the call sites here will be replaced
with `from services import ai_helpers` and request-bound invocations.

PII safety:
  * Returns no operator/tenant/user identifiers.
  * All copy is operator-published (`gettext_lazy`) or honest "—" placeholders.
  * Real wiring MUST route through `services.ai_helpers.invoke_with_request`
    so PII inference + graceful degradation are honored — direct
    `services.ai_gateway` import is forbidden in app code (enforced by
    `scripts/scan_ai_gateway_boundary.py`).

Determinism:
  * The stub returns a fresh dict per call (mutation-safe).
  * Tests can assert exact shape and copy without flakiness.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

__all__ = [
    "build_copilot_rail_payload",
    "build_copilot_suggestion_card",
    "build_copilot_activity_event",
]


def build_copilot_suggestion_card(
    *,
    title: str = "",
    summary: str = "",
    cta_label: str = "",
    cta_action: str = "",
    severity: str = "info",
) -> dict[str, Any]:
    """Render a single AI suggestion card.

    Shape (matches `_ai_copilot_rail.html` partial):
        title       str
        summary     str
        cta_label   str
        cta_action  str  — operator routes this string in their JS click handler
                          (e.g. "open:billing/invoice/123" or "ack:abandon").
                          We don't open URLs from this stub — operator owns the
                          handler so unsanctioned navigation is impossible.
        severity    str  — ok / warn / danger / info
    """
    return {
        "title": title,
        "summary": summary,
        "cta_label": cta_label,
        "cta_action": cta_action,
        "severity": severity,
    }


def build_copilot_activity_event(
    *,
    icon: str = "•",
    text: str = "",
    time_label: str = "",
    severity: str = "info",
) -> dict[str, Any]:
    """Render a single activity event for the rail's "recent" strip."""
    return {
        "icon": icon,
        "text": text,
        "time_label": time_label,
        "severity": severity,
    }


def build_copilot_rail_payload(*, request: Any | None = None) -> dict[str, Any]:
    """Return the full copilot rail payload (honest stub for v3.57.0).

    Real implementation in v3.58+ MUST:
      1. Resolve the operator's request-bound AI runtime config via
         `services.ai_helpers.is_ai_available(request.school)`.
      2. When available, invoke via `services.ai_helpers.invoke_with_request`
         with a stable `northstar_prompt_type="copilot_rail"` for daily rollup.
      3. Fall back to this stub's shape on any failure path — never raise.

    Shape consumed by the partial (cockpit.ai_copilot_rail.* keys):
        enabled           bool
        intro_text        str
        suggestions       list[suggestion_card]
        activity          list[activity_event]
        shortcut_hint     str   — e.g. "Cmd/Ctrl + K"
        empty_state_text  str   — shown when suggestions+activity are both empty
        deferred_marker   str   — "v3.57-honest-stub" so audit tooling can spot
                                  unwired copilot surfaces in production
    """
    # NOTE: `request` is accepted to keep the v3.58+ contract stable. We don't
    # touch it from the stub — but the caller (orchestrator) can already pass
    # it without later refactoring once real wiring lands.
    _ = request
    return {
        "enabled": False,
        "intro_text": _("Operator copilot"),
        "suggestions": [],
        "activity": [],
        "shortcut_hint": "Cmd/Ctrl + K",
        "empty_state_text": _("No copilot suggestions yet."),
        "deferred_marker": "v3.57-honest-stub",
    }
