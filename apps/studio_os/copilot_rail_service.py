"""Studio OS Co-pilot Rail — persistent AI presence service (v3.53.1, 2026-05-21).

Backs the right-side cockpit rail that turns the static co-pilot partial into
an ambient, context-aware AI presence. Three concerns live here:

1. **Context snapshot.** Build a small server-side dataclass describing
   what the operator is doing right now (mode, hashed school slug, surface
   name, optional selection summary, posture mode). Tenant slug is never
   logged or returned raw — only the sha256[:8] prefix lands in payloads.

2. **Insights pulse.** Generate 3 short contextual hints rotating every
   90 seconds (or on `rmc:cockpit:context-changed`). Cloud-first via
   ``services.ai_helpers.invoke_with_request(...)`` with the
   ``STUDIO_OS_ASSISTANT`` task type. When the gateway returns ``None``
   (AI policy disabled, provider unreachable, or PII-redacted input
   short-circuit) we fall back to deterministic rules-layer insights so
   the panel never goes blank. Every insight carries a ``source`` tag
   so the UI can show provenance.

3. **Quick actions.** Pull from the universal command-bar registry
   (``apps.siteconfig.command_bar_registry.get_actions_for_user``)
   and filter to the current surface_name + cap at 6 entries. Pure
   passthrough — we never invent URLs.

Boundary contract (CLAUDE.md):

  * App code routes AI through ``services.ai_helpers``, never
    ``services.ai_gateway`` directly.
  * Cloud-first. Ollama is edge-only; this module never assumes a
    Render-hosted Ollama and never selects a backend itself — the
    gateway's deployment-posture chain owns that.
  * Tenant-scoped. Insights are filtered by ``request.school`` and we
    never include cross-tenant references in the prompt or rendered
    body. Reject responses that mention other tenant slugs.
  * No PII in logs — only the hashed slug prefix.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass
from typing import Any, Literal

from services.ai_helpers import invoke_with_request

logger = logging.getLogger(__name__)

PostureMode = Literal["live_cloud", "live_local", "guided", "unavailable"]
InsightSource = Literal["cloud", "rules", "fallback"]

# Cap quick-actions visible on the rail to keep the surface scannable.
MAX_QUICK_ACTIONS = 6

# Module-stable surface names the rail recognizes. The rail still works for
# unknown surfaces — they get the "shell" bucket — but these are the named
# buckets the rules-layer insights know how to specialize on.
KNOWN_SURFACE_NAMES = frozenset(
    {
        "shell",
        "experience",
        "automation",
        "output",
        "launch",
        "control",
    }
)


@dataclass(frozen=True)
class CopilotContextSnapshot:
    """Server-side context the rail needs to render and prompt against.

    The school slug is never carried raw — only ``school_slug_hash``
    (sha256[:8]) is included so the dataclass can be safely serialized to
    JSON and logged.
    """

    mode: str
    school_slug_hash: str
    surface_name: str
    selection_summary: str | None
    posture_mode: PostureMode

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CopilotInsight:
    """One rotating insight pill displayed inside the rail."""

    id: str
    title: str
    body: str
    source: InsightSource
    priority: int = 50

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Snapshot construction
# ---------------------------------------------------------------------------


def _hash_school_slug(school: Any | None) -> str:
    """Return sha256[:8] of the school slug, or ``"none"`` when no tenant."""
    if school is None:
        return "none"
    slug = getattr(school, "slug", None) or getattr(school, "code", None) or ""
    if not slug:
        return "none"
    return hashlib.sha256(str(slug).encode("utf-8")).hexdigest()[:8]


def _resolve_surface_name(mode: str | None, request: Any) -> str:
    """Map (mode, request) -> coarse surface identifier."""
    mode_norm = (mode or "").strip().lower()
    if mode_norm in KNOWN_SURFACE_NAMES:
        return mode_norm
    return "shell"


def _resolve_posture_mode(request: Any) -> PostureMode:
    """Probe the AI posture without binding the rail to a specific provider.

    Uses the allowlisted infrastructure entry point in ``apps.portal`` — that
    module IS allowed to import ``services.ai_gateway``; app code (this
    module) is not.
    """
    try:
        from apps.portal.ai_provider import probe_ai_provider_reachable

        health = probe_ai_provider_reachable() or {}
    except Exception:  # noqa: BLE001
        logger.debug("copilot_rail: posture probe failed", exc_info=True)
        return "unavailable"
    raw_posture = str(health.get("posture_mode") or "").strip().lower()
    if raw_posture in {"live_cloud", "live_local", "guided", "unavailable"}:
        return raw_posture  # type: ignore[return-value]
    # Fall back to derive from reachability / fallback flags.
    if health.get("reachable") and health.get("provider") == "litellm":
        return "live_cloud"
    if health.get("reachable") and health.get("provider") == "ollama":
        return "live_local"
    if health.get("rules_fallback_enabled") or health.get("fallback_active"):
        return "guided"
    return "unavailable"


def _resolve_selection_summary(request: Any) -> str | None:
    """Best-effort short label for the current selection (tour token / query)."""
    if request is None:
        return None
    try:
        params = getattr(request, "GET", None)
        if params is not None:
            for key in ("selection", "tour", "step", "section"):
                value = params.get(key)
                if value:
                    return str(value)[:48]
    except (AttributeError, TypeError, ValueError):
        return None
    return None


def build_context_snapshot(request: Any, *, mode: str) -> CopilotContextSnapshot:
    """Resolve the operator's current context into a tenant-safe snapshot."""
    school = getattr(request, "school", None) if request is not None else None
    return CopilotContextSnapshot(
        mode=(mode or "").strip().lower() or "shell",
        school_slug_hash=_hash_school_slug(school),
        surface_name=_resolve_surface_name(mode, request),
        selection_summary=_resolve_selection_summary(request),
        posture_mode=_resolve_posture_mode(request),
    )


# ---------------------------------------------------------------------------
# Insights — cloud first, rules fallback
# ---------------------------------------------------------------------------


_RULES_INSIGHTS_BY_SURFACE: dict[str, tuple[tuple[str, str, str], ...]] = {
    "shell": (
        ("studio-overview", "Pick a mode", "Open Experience, Automation, Outputs, Launch, or Control to scope your work."),
        ("studio-commands", "Press ⌘K", "Universal command bar finds every action you have permission to run."),
        ("studio-blueprint", "Use a blueprint", "Theme + module + workflow packs ship as one install — preview before publish."),
    ),
    "experience": (
        ("exp-palette", "Generate palette", "AI suggests palettes from your logo, then runs WCAG contrast before publish."),
        ("exp-compare", "Compare themes", "Side-by-side any two versions; rollback is one click in version history."),
        ("exp-tokens", "Edit semantic tokens", "Surface / text / hairline tokens flow to every shell — no per-page hex literals."),
    ),
    "automation": (
        ("auto-simulate", "Simulate first", "Run a dry-run on a workflow before activating to catch loops and conflicts."),
        ("auto-natural", "Describe in plain English", "Natural-language workflow builder turns intent into a draft you can review."),
        ("auto-staged", "Stage activation", "Roll a workflow to one cohort, watch SLO, then expand — no big-bang flips."),
    ),
    "output": (
        ("out-branding", "Inherit branding", "Report cards & documents auto-pull theme tokens — set branding once."),
        ("out-policy", "Check policy registry", "Field-level redaction and retention rules apply to every export."),
        ("out-dependency", "Map dependencies", "See which reports depend on which fields before deprecating a column."),
    ),
    "launch": (
        ("launch-preview", "Preview by role", "Open admin / teacher / parent / student previews before go-live."),
        ("launch-checklist", "Run launch checklist", "Day-1 readiness pulls from data import, role mapping, and notifications."),
        ("launch-plan", "Pick a plan", "Plan choice gates module visibility — match plan to onboarding scope."),
    ),
    "control": (
        ("ctl-audit", "Review audit before rollback", "Every feature flip is logged — read the audit before reversing."),
        ("ctl-impact", "Run impact analysis", "Feature changes affect portal and backend — preview impact first."),
        ("ctl-rbac", "Verify RBAC", "Permission changes propagate immediately — confirm with a role preview."),
    ),
}


def _rules_fallback_insights(
    snapshot: CopilotContextSnapshot,
    *,
    n: int = 3,
) -> list[CopilotInsight]:
    """Deterministic rules-layer fallback when the AI gateway is unavailable."""
    bucket = _RULES_INSIGHTS_BY_SURFACE.get(snapshot.surface_name, _RULES_INSIGHTS_BY_SURFACE["shell"])
    out: list[CopilotInsight] = []
    for idx, (insight_id, title, body) in enumerate(bucket[:n]):
        priority = 60 - idx
        # Slight posture-aware tweak so the panel acknowledges the mode without
        # leaking any tenant detail.
        if snapshot.posture_mode == "unavailable" and idx == 0:
            body = body + " (AI offline — guided suggestions only.)"
        out.append(
            CopilotInsight(
                id=insight_id,
                title=title,
                body=body,
                source="rules",
                priority=priority,
            )
        )
    return out


def _build_insight_prompt(snapshot: CopilotContextSnapshot, *, n: int) -> str:
    """Build a tenant-safe prompt — only the hashed slug is included.

    The prompt explicitly forbids the model from inventing tenant names so
    even on a creative drift the rendered body cannot leak a foreign tenant.
    """
    selection_hint = (snapshot.selection_summary or "(no specific selection)")[:80]
    return (
        "You are the Studio OS co-pilot rail. Generate "
        f"{n} short, action-oriented insights for the operator who is working in "
        f"the '{snapshot.surface_name}' surface (mode='{snapshot.mode}'). "
        f"Their tenant fingerprint is {snapshot.school_slug_hash} — do NOT invent "
        "tenant names, school slugs, or cross-tenant references. "
        f"Active selection: {selection_hint}. "
        "Respond as a JSON object with key 'insights' whose value is a list of "
        "{id, title, body} entries. Title 4-6 words; body one sentence under 140 chars."
    )


def _parse_cloud_response(raw_text: str, *, n: int) -> list[tuple[str, str, str]] | None:
    """Best-effort parser: model is asked for JSON but we accept loose output."""
    import json
    import re

    if not raw_text:
        return None
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    items = obj.get("insights") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        return None
    parsed: list[tuple[str, str, str]] = []
    for idx, entry in enumerate(items[:n]):
        if not isinstance(entry, dict):
            continue
        insight_id = str(entry.get("id") or f"cloud-{idx}")[:48]
        title = str(entry.get("title") or "").strip()[:60]
        body = str(entry.get("body") or "").strip()[:200]
        if not title or not body:
            continue
        parsed.append((insight_id, title, body))
    return parsed or None


def _looks_like_cross_tenant_leak(
    insights: list[tuple[str, str, str]],
    snapshot: CopilotContextSnapshot,
    *,
    request: Any,
) -> bool:
    """Reject rendered content that mentions a slug the operator's tenant doesn't own.

    We don't have a list of *other* tenants on hand, but we can do a cheap
    structural check: any token that looks like a slug AND isn't the
    operator's own slug is suspicious. Combined with the prompt-side
    instruction this is defense in depth.
    """
    own_slug = ""
    school = getattr(request, "school", None) if request is not None else None
    if school is not None:
        own_slug = str(getattr(school, "slug", "") or "")
    if not own_slug:
        return False
    import re

    slug_re = re.compile(r"\bschool[-_:/][a-z0-9-]{2,32}\b", re.IGNORECASE)
    for _id, title, body in insights:
        for token in slug_re.findall(title + " " + body):
            normalized = token.split(":", 1)[-1].split("/", 1)[-1]
            normalized = normalized.replace("school-", "").replace("school_", "")
            if normalized and normalized.lower() != own_slug.lower():
                return True
    return False


def generate_insights(
    snapshot: CopilotContextSnapshot,
    *,
    request: Any,
    n: int = 3,
) -> list[CopilotInsight]:
    """Return ``n`` insights for the current snapshot.

    Cloud-first: calls ``services.ai_helpers.invoke_with_request`` with the
    ``STUDIO_OS_ASSISTANT`` task. Falls back deterministically to the
    rules-layer when AI is unavailable, the response is unparseable, or the
    response looks like it leaks a cross-tenant slug.
    """
    n = max(1, min(int(n), 6))
    if snapshot.posture_mode in ("unavailable",):
        # No point hitting the gateway — short-circuit to rules.
        return _rules_fallback_insights(snapshot, n=n)

    prompt = _build_insight_prompt(snapshot, n=n)
    permissions = {}
    if request is not None:
        try:
            from services.ai_copilot_rbac import (
                build_copilot_permissions,
                rbac_directives_for_permissions,
            )

            permissions = build_copilot_permissions(getattr(request, "user", None), request=request)
            host_kind = getattr(request, "public_host_kind", None)
            active_url = str(getattr(request, "path", "") or "")
            directives = rbac_directives_for_permissions(
                permissions,
                active_url=active_url,
                host_kind=host_kind,
            )
            if directives:
                prompt = f"{directives}\n\n{prompt}"
        except Exception:
            permissions = {}
    metadata = {
        "northstar_prompt_type": "studio_os_copilot_rail",
        "content_sensitivity": "standard",
        "surface_name": snapshot.surface_name,
        "tenant_fingerprint": snapshot.school_slug_hash,
        "request": request,
        "permissions": permissions,
        "rbac_scope": permissions.get("scope") if permissions else "general",
        "copilot_rbac_enforced": True,
        "surface": "studio_os_copilot_rail_insights",
    }

    try:
        result = invoke_with_request(
            task_type="STUDIO_OS_ASSISTANT",
            prompt=prompt,
            request=request,
            user_query="",
            metadata=metadata,
        )
    except Exception:  # noqa: BLE001
        logger.debug(
            "copilot_rail: gateway invoke errored for tenant=%s surface=%s",
            snapshot.school_slug_hash,
            snapshot.surface_name,
            exc_info=True,
        )
        return _rules_fallback_insights(snapshot, n=n)

    if result is None:
        # Gateway short-circuited (policy off / provider unreachable / PII).
        return _rules_fallback_insights(snapshot, n=n)

    raw_text, _meta = result
    text = raw_text if isinstance(raw_text, str) else str(raw_text or "")
    parsed = _parse_cloud_response(text, n=n)
    if not parsed:
        logger.info(
            "copilot_rail: cloud response unparseable for tenant=%s surface=%s — falling back",
            snapshot.school_slug_hash,
            snapshot.surface_name,
        )
        return _rules_fallback_insights(snapshot, n=n)

    if _looks_like_cross_tenant_leak(parsed, snapshot, request=request):
        logger.warning(
            "copilot_rail: cross-tenant leak suspected in cloud response for tenant=%s — falling back",
            snapshot.school_slug_hash,
        )
        return _rules_fallback_insights(snapshot, n=n)

    out: list[CopilotInsight] = []
    for idx, (insight_id, title, body) in enumerate(parsed):
        out.append(
            CopilotInsight(
                id=insight_id,
                title=title,
                body=body,
                source="cloud",
                priority=70 - idx,
            )
        )
    if len(out) < n:
        # Top up from rules so the panel keeps a stable 3-row shape.
        topup = _rules_fallback_insights(snapshot, n=n - len(out))
        out.extend(topup)
    return out


# ---------------------------------------------------------------------------
# Quick actions — registry passthrough filtered by surface
# ---------------------------------------------------------------------------


_SURFACE_ACTION_KIND_PRIORITY: dict[str, tuple[str, ...]] = {
    "experience": ("palette", "settings", "install", "deploy", "navigate", "health"),
    "automation": ("settings", "navigate", "deploy", "health"),
    "output": ("settings", "navigate", "deploy", "health"),
    "launch": ("settings", "navigate", "deploy", "health"),
    "control": ("health", "settings", "navigate"),
    "shell": ("navigate", "settings", "palette", "install", "deploy", "health"),
}


def _action_matches_surface(action_url: str, surface_name: str) -> bool:
    """Cheap URL-substring scoring so we can prioritize on-surface actions."""
    if not action_url:
        return False
    needle = surface_name.lower()
    if needle == "shell":
        return True
    return needle in action_url.lower()


def resolve_quick_actions(
    snapshot: CopilotContextSnapshot,
    *,
    request: Any,
) -> list[dict[str, Any]]:
    """Return up to ``MAX_QUICK_ACTIONS`` actions filtered to the current surface.

    Pure passthrough on top of the universal command-bar registry —
    permissions and tenant scoping live there. We add: surface-relevance
    ranking and a hard cap of 6.
    """
    if request is None:
        return []
    try:
        from apps.siteconfig.command_bar_registry import (
            get_actions_for_user,
            serialize_actions,
        )
    except Exception:  # noqa: BLE001
        logger.debug("copilot_rail: command_bar_registry import failed", exc_info=True)
        return []

    user = getattr(request, "user", None)
    school = getattr(request, "school", None)
    try:
        all_actions = get_actions_for_user(user, school)
    except Exception:  # noqa: BLE001
        logger.debug(
            "copilot_rail: get_actions_for_user failed for tenant=%s",
            snapshot.school_slug_hash,
            exc_info=True,
        )
        return []

    kind_priority = _SURFACE_ACTION_KIND_PRIORITY.get(
        snapshot.surface_name, _SURFACE_ACTION_KIND_PRIORITY["shell"]
    )

    def _rank(action: Any) -> tuple[int, int]:
        kind = getattr(action, "kind", "") or ""
        url = getattr(action, "url", "") or ""
        try:
            kind_rank = kind_priority.index(kind)
        except ValueError:
            kind_rank = len(kind_priority)
        surface_match = 0 if _action_matches_surface(url, snapshot.surface_name) else 1
        return (surface_match, kind_rank)

    ranked = sorted(all_actions, key=_rank)
    capped = ranked[:MAX_QUICK_ACTIONS]
    return serialize_actions(capped)


# ---------------------------------------------------------------------------
# Top-level orchestration helpers (used by views)
# ---------------------------------------------------------------------------


def build_rail_payload(request: Any, *, mode: str, n: int = 3) -> dict[str, Any]:
    """Convenience: returns the full {snapshot, insights, quick_actions, registry} dict.

    ``registry`` is a separate channel (operator-only) carrying governance state
    from the Feature Gap + Backlog registries — kept out of ``insights`` so the
    AI-insight contract (exactly ``n`` rows) is unchanged.
    """
    snapshot = build_context_snapshot(request, mode=mode)
    insights = generate_insights(snapshot, request=request, n=n)
    quick_actions = resolve_quick_actions(snapshot, request=request)
    try:
        from apps.studio_os.copilot_registry_insights import build_registry_insights

        registry = build_registry_insights(request)
    except Exception:  # noqa: BLE001 — registry bridge must never break the rail
        logger.debug("copilot_rail: registry insights failed", exc_info=True)
        registry = []
    return {
        "snapshot": snapshot.to_dict(),
        "insights": [i.to_dict() for i in insights],
        "quick_actions": quick_actions,
        "registry": registry,
    }


__all__ = (
    "CopilotContextSnapshot",
    "CopilotInsight",
    "MAX_QUICK_ACTIONS",
    "build_context_snapshot",
    "build_rail_payload",
    "generate_insights",
    "resolve_quick_actions",
)
