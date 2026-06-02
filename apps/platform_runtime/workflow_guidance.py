"""Workflow guidance service — runtime helpers for the workflow-info components.

Phase 3 deliverable. Maps an incoming Django ``HttpRequest`` against the static
``workflow_registry.WORKFLOWS`` table and produces the small data dicts the
four scaffolded components expect:

* ``get_workflow(key)``                    static lookup
* ``resolve_workflow_for_route(request)``  best-effort URL-name match
* ``next_action_for(request, workflow)``   dict ready for workflow_next_action.html
* ``tags_for(request, workflow)``          list[dict] ready for workflow_info_tag.html
* ``is_visible_for(request, workflow)``    3-layer host / enable / override gate

This module is intentionally pure — no DB writes, no AI calls, no external
network IO. Callers compose the returned data into context the workflow page
template renders. The Phase 4 wiring wave plugs these into the relevant
shells / views.

Tenant-safety:
  ``is_visible_for`` returns False on tenant hosts for any workflow tagged
  ``platform-only`` (per the 19-tag taxonomy). Downstream templates must
  still skip rendering — defense in depth.

Role-string contract:
  Audience values defined in ``workflow_registry`` are surface-kind labels,
  not Django role strings. Anywhere this module compares to Django's
  ``User.Role`` (none of the current helpers do), it routes through
  ``apps.platform_runtime.role_registry`` per the no-hardcoding contract.
"""

from __future__ import annotations

import re

from typing import Any, Optional

from django.utils.translation import gettext_lazy as _

from .workflow_registry import (
    ALL_TAGS,
    AUDIENCE_FOUNDER,
    AUDIENCE_OPERATOR,
    AUDIENCE_PARENT,
    AUDIENCE_PUBLIC,
    AUDIENCE_STUDENT,
    AUDIENCE_TEACHER,
    AUDIENCE_TENANT_ADMIN,
    TAG_AI_HELP_AVAILABLE,
    TAG_APPROVAL_REQUIRED,
    TAG_AUDIT_LOGGED,
    TAG_BILLING_IMPACT,
    TAG_BLOCKS_LAUNCH,
    TAG_DATA_QUALITY_ISSUE,
    TAG_DRAFT,
    TAG_EXTERNAL_REQUIRED,
    TAG_MANUAL_FALLBACK,
    TAG_MISSING_SETUP,
    TAG_NEEDS_REVIEW,
    TAG_NOT_REVERSIBLE,
    TAG_OPTIONAL,
    TAG_PLATFORM_ONLY,
    TAG_PREVIEW_AVAILABLE,
    TAG_PUBLISHED,
    TAG_READY_TO_LAUNCH,
    TAG_REQUIRED,
    TAG_REVERSIBLE,
    TAG_TENANT_SAFE,
    WORKFLOWS,
    WorkflowDefinition,
)


# ============================================================
# Translated tag labels.
#
# Kept here (not in workflow_registry) so the registry is a pure data
# module and the i18n catalog only sees these strings when the service
# layer is imported. Each label maps one of the 19 taxonomy slugs to a
# translated short label suitable for the chip.
# ============================================================

_TAG_LABELS: dict[str, Any] = {
    TAG_REQUIRED: _("Required"),
    TAG_OPTIONAL: _("Optional"),
    TAG_BLOCKS_LAUNCH: _("Blocks launch"),
    TAG_NEEDS_REVIEW: _("Needs review"),
    TAG_TENANT_SAFE: _("Tenant safe"),
    TAG_PLATFORM_ONLY: _("Platform only"),
    TAG_PREVIEW_AVAILABLE: _("Preview available"),
    TAG_APPROVAL_REQUIRED: _("Approval required"),
    TAG_EXTERNAL_REQUIRED: _("External required"),
    TAG_MANUAL_FALLBACK: _("Manual fallback"),
    TAG_AI_HELP_AVAILABLE: _("AI help available"),
    TAG_DATA_QUALITY_ISSUE: _("Data quality issue"),
    TAG_BILLING_IMPACT: _("Billing impact"),
    TAG_AUDIT_LOGGED: _("Audit logged"),
    TAG_REVERSIBLE: _("Reversible"),
    TAG_NOT_REVERSIBLE: _("Not reversible"),
    TAG_DRAFT: _("Draft"),
    TAG_PUBLISHED: _("Published"),
    TAG_MISSING_SETUP: _("Missing setup"),
    TAG_READY_TO_LAUNCH: _("Ready to launch"),
}

# Tone hints per tag. Color is decorative; the visible text label always
# carries the meaning. Tones map to the `data-rmc-workflow-tag-tone`
# attribute consumed by `rmc-workflow-guidance.css`.
_TAG_TONES: dict[str, str] = {
    TAG_REQUIRED: "warn",
    TAG_OPTIONAL: "neutral",
    TAG_BLOCKS_LAUNCH: "danger",
    TAG_NEEDS_REVIEW: "warn",
    TAG_TENANT_SAFE: "info",
    TAG_PLATFORM_ONLY: "info",
    TAG_PREVIEW_AVAILABLE: "info",
    TAG_APPROVAL_REQUIRED: "warn",
    TAG_EXTERNAL_REQUIRED: "warn",
    TAG_MANUAL_FALLBACK: "info",
    TAG_AI_HELP_AVAILABLE: "info",
    TAG_DATA_QUALITY_ISSUE: "warn",
    TAG_BILLING_IMPACT: "warn",
    TAG_AUDIT_LOGGED: "info",
    TAG_REVERSIBLE: "success",
    TAG_NOT_REVERSIBLE: "warn",
    TAG_DRAFT: "neutral",
    TAG_PUBLISHED: "success",
    TAG_MISSING_SETUP: "danger",
    TAG_READY_TO_LAUNCH: "success",
}


def _host_kind(request: Any) -> str:
    """Best-effort host-kind extraction.

    Mirrors the cockpit_context pattern: the platform attaches
    ``public_host_kind`` to the request via middleware
    (apps/siteconfig/middleware.py). Defaults to ``"tenant"`` for safety
    so any unknown surface is treated as a tenant host (i.e. platform-only
    workflows are HIDDEN by default, never silently leaked).
    """
    if request is None:
        return "tenant"
    kind = getattr(request, "public_host_kind", None)
    if isinstance(kind, str) and kind:
        return kind
    return "tenant"


# ============================================================
# Public helpers.
# ============================================================


def get_workflow(key: str) -> Optional[WorkflowDefinition]:
    """Return the workflow with ``key`` or ``None``."""
    if not isinstance(key, str):
        return None
    return WORKFLOWS.get(key)


_TENANT_PATH_PREFIX_RE = re.compile(r"^/t/[^/]+")


def normalize_path_for_workflow_registry(path: str) -> str:
    """Strip ``/t/<tenant-slug>/`` so matrix ``entry_path`` prefixes match tenant URLs."""

    normalized = path if path.startswith("/") else f"/{path}"
    match = _TENANT_PATH_PREFIX_RE.match(normalized)
    if not match:
        return normalized
    suffix = normalized[match.end() :] or "/"
    return suffix if suffix.startswith("/") else f"/{suffix}"


def resolve_workflow_for_entry_path(path: str) -> Optional[WorkflowDefinition]:
    """Longest-prefix match on registry ``entry_path`` (tenant-aware)."""

    normalized = normalize_path_for_workflow_registry(path or "")
    if not normalized:
        return None
    best_match: Optional[WorkflowDefinition] = None
    best_length = -1
    for workflow in WORKFLOWS.values():
        ep = getattr(workflow, "entry_path", None)
        if not ep or not isinstance(ep, str):
            continue
        if normalized.startswith(ep) and len(ep) > best_length:
            best_match = workflow
            best_length = len(ep)
    return best_match


def resolve_workflow_for_route(request: Any) -> Optional[WorkflowDefinition]:
    """Best-effort lookup: find a workflow whose ``route`` matches the request's URL name.

    Returns ``None`` when:
      * request is missing
      * resolver_match is unavailable (e.g. middleware ran before URL resolution)
      * no workflow with that URL name is registered

    Defensive: never raises on a missing attribute. Callers wrap context
    builds in this helper without needing further error handling.
    """
    if request is None:
        return None
    match = getattr(request, "resolver_match", None)
    view_name = getattr(match, "view_name", None) if match is not None else None
    if isinstance(view_name, str) and view_name:
        for workflow in WORKFLOWS.values():
            if workflow.route == view_name:
                return workflow
    # Fallback for matrix-promoted entries whose ``route`` is a URL path
    # (e.g. ``/super/schools/create/``) rather than a view name.
    path = getattr(request, "path", None)
    if isinstance(path, str) and path:
        return resolve_workflow_for_entry_path(path)
    return None


def is_visible_for(request: Any, workflow: WorkflowDefinition) -> bool:
    """3-layer host / enable / override visibility gate.

    Layer 1 — host gate:
        ``platform-only`` workflows are HIDDEN on tenant hosts. Workflows
        whose audience is operator/founder are HIDDEN on tenant hosts.
        Tenant-audience workflows are HIDDEN on the operator host.

    Layer 2 — enable gate (placeholder for Phase 4):
        Reserved for ``SiteSettings.cockpit_payload.workflow_guidance.*``
        per-section enable flags landed in Phase 4+. Until that lands,
        the layer is a no-op and returns True so scaffolding renders the
        moment the operator wires it.

    Layer 3 — page-block override (template responsibility):
        The caller template wraps the include in a ``{% block %}`` so
        per-page overrides can suppress the component without code change.
        Not enforced here.
    """
    if workflow is None:
        return False
    host = _host_kind(request)

    # Layer 1 — host gate.
    if TAG_PLATFORM_ONLY in workflow.default_tags and host == "tenant":
        return False
    if workflow.audience in (AUDIENCE_OPERATOR, AUDIENCE_FOUNDER) and host == "tenant":
        return False
    if (
        workflow.audience
        in (
            AUDIENCE_TENANT_ADMIN,
            AUDIENCE_TEACHER,
            AUDIENCE_PARENT,
            AUDIENCE_STUDENT,
        )
        and host == "manager"
    ):
        return False
    if workflow.audience == AUDIENCE_PUBLIC and host not in ("public", "marketing"):
        # public workflows surface on the marketing host only
        return False

    # Layer 2 — enable gate (placeholder).
    # site = getattr(request, "site_settings", None) or getattr(request, "SITE", None)
    # if site is not None and isinstance(getattr(site, "cockpit_payload", None), dict):
    #     enabled = (
    #         site.cockpit_payload
    #         .get("workflow_guidance", {})
    #         .get(workflow.key, {})
    #         .get("enabled", True)
    #     )
    #     if enabled is False:
    #         return False

    return True


def tags_for(request: Any, workflow: WorkflowDefinition) -> list[dict[str, Any]]:
    """Build the tag list for ``workflow``, suitable for ``workflow_info_tag.html``.

    The list is composed of:
      * ``workflow.default_tags`` — static taxonomy slugs from the registry.
      * Dynamic tags injected based on workflow shape:
          - ``external-required`` when ``external_blockers`` is non-empty.
          - ``audit-logged``      when ``related_audit_event`` is set.
          - ``ai-help-available`` when ``related_ai_context_key`` is set.

    Tags are de-duplicated, preserving insertion order. ``platform-only``
    is suppressed on tenant hosts so the tag never leaks to a tenant user
    (defense in depth on top of ``is_visible_for``).
    """
    if workflow is None:
        return []
    host = _host_kind(request)

    seen: set[str] = set()
    ordered: list[str] = []

    def _push(slug: str) -> None:
        if slug in ALL_TAGS and slug not in seen:
            seen.add(slug)
            ordered.append(slug)

    for slug in workflow.default_tags:
        _push(slug)

    if workflow.external_blockers:
        _push(TAG_EXTERNAL_REQUIRED)
    if workflow.related_audit_event:
        _push(TAG_AUDIT_LOGGED)
    if workflow.related_ai_context_key:
        _push(TAG_AI_HELP_AVAILABLE)

    # Defense-in-depth: never emit platform-only on a tenant host even if
    # the registry declared it. is_visible_for should have suppressed the
    # whole render already, but a callsite that bypasses the visibility
    # gate must still not leak the marker.
    if host == "tenant" and TAG_PLATFORM_ONLY in seen:
        ordered = [slug for slug in ordered if slug != TAG_PLATFORM_ONLY]

    return [
        {
            "key": slug,
            "label": _TAG_LABELS.get(slug, slug),
            "tone": _TAG_TONES.get(slug, "neutral"),
        }
        for slug in ordered
    ]


def next_action_for(request: Any, workflow: WorkflowDefinition) -> Optional[dict[str, Any]]:
    """Build the next-action payload for ``workflow_next_action.html``.

    Returns ``None`` when the workflow is hidden or has no actionable next
    step (e.g. operator-only workflow on a tenant host). Otherwise returns
    a dict shaped to the template contract.

    The shape returned here is conservative: it surfaces the workflow's
    own route as the primary action and uses ``related_help_article`` (when
    set) as the secondary action's target. Per-tenant dynamic state
    (e.g. "currently blocked by missing payment provider") lives in the
    workflow's owning app — this helper only carries the static skeleton.
    """
    if workflow is None or not is_visible_for(request, workflow):
        return None

    primary: dict[str, Any] = {
        "label": workflow.title,
        # Route resolution deferred to the template; the template renders
        # ``{% url 'route' %}`` via the calling view's context.
        "url": "",
        "task_code": workflow.module,
        "step": "open",
    }

    secondary: Optional[dict[str, Any]] = None
    if workflow.related_help_article:
        secondary = {
            "label": _("Learn how this works"),
            "url": "",
            "task_code": workflow.module,
            "step": "help",
        }

    blocker: Optional[dict[str, Any]] = None
    if workflow.external_blockers:
        blocker = {
            "label": workflow.external_blockers[0],
            "tone": "warn",
        }

    state = "blocked" if blocker else "ready"

    payload: dict[str, Any] = {
        "primary": primary,
        "secondary": secondary,
        "blocker": blocker,
        "state": state,
    }

    # Owner badge: a coarse-grained kind drawn from the audience. Never a
    # raw user identity — PII-safe by construction.
    if workflow.audience in (AUDIENCE_OPERATOR, AUDIENCE_FOUNDER):
        payload["owner"] = {"label": _("Platform team"), "kind": "team"}
    elif workflow.audience == AUDIENCE_TENANT_ADMIN:
        payload["owner"] = {"label": _("School admin"), "kind": "operator"}
    elif workflow.audience == AUDIENCE_TEACHER:
        payload["owner"] = {"label": _("Teacher"), "kind": "tenant"}
    elif workflow.audience == AUDIENCE_PARENT:
        payload["owner"] = {"label": _("Parent / guardian"), "kind": "tenant"}
    elif workflow.audience == AUDIENCE_STUDENT:
        payload["owner"] = {"label": _("Student"), "kind": "tenant"}

    if workflow.related_ai_context_key:
        payload["ai_context_key"] = workflow.related_ai_context_key
        try:
            from django.urls import reverse

            payload["ai_help_url"] = reverse("feedback:help_center") + "?focus=ai"
        except Exception:
            payload["ai_help_url"] = ""

    return payload


def help_panel_for(request: Any, workflow: WorkflowDefinition) -> Optional[dict[str, Any]]:
    """Build the help panel payload for ``workflow_help_panel.html``.

    Composes ``how_it_works`` from the workflow's step list,
    ``before_you_start`` from prerequisites, ``common_blockers`` from
    ``external_blockers``, ``what_happens_next`` from ``success_state``,
    and ``need_help`` from the help article + AI context key when set.

    Returns ``None`` when the workflow is hidden.
    """
    if workflow is None or not is_visible_for(request, workflow):
        return None

    how_it_works: list[Any] = [s.title for s in workflow.steps]
    common_blockers: list[dict[str, Any]] = [
        {"label": text, "fix_url": ""} for text in workflow.external_blockers
    ]
    what_happens_next: list[Any] = (
        [workflow.success_state] if workflow.success_state else []
    )

    need_help: Optional[dict[str, Any]] = None
    if workflow.related_help_article or workflow.related_ai_context_key:
        need_help = {
            "label": _("Need help?"),
            "url": "",
        }
        if workflow.related_ai_context_key:
            need_help["ai_help"] = {
                "label": _("Ask the AI assistant"),
                "context_key": workflow.related_ai_context_key,
            }

    return {
        "title": workflow.title,
        "subtitle": workflow.purpose,
        "how_it_works": how_it_works,
        "before_you_start": list(workflow.prerequisites),
        "common_blockers": common_blockers,
        "what_happens_next": what_happens_next,
        "need_help": need_help,
    }


__all__ = [
    "get_workflow",
    "resolve_workflow_for_route",
    "is_visible_for",
    "tags_for",
    "next_action_for",
    "help_panel_for",
]
