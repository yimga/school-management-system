"""Workflow-aware AI invoker — bridges the workflow registry to ``services.ai_helpers``.

Phase 8 Wave F. Provides ``invoke_with_workflow_context``, a thin wrapper
around ``services.ai_helpers.invoke_with_request`` that:

1. Resolves a workflow via ``apps.platform_runtime.ai_workflow_bridge.bind_workflow_context_for_ai``
   (DATA DEFAULTER posture when nothing resolves).
2. Merges the workflow's structured context (key / title / route / audience /
   host_kind / ai_context_key) into the ``metadata`` dict the gateway already
   normalizes.
3. Delegates the actual gateway call to ``invoke_with_request`` so the
   architectural boundary at ``scan_ai_gateway_boundary.py`` is preserved —
   this module does NOT import ``services.ai_gateway`` directly.

App code that wants AI assistance for a workflow imports THIS module, not
the gateway. Existing AI surfaces (Studio OS copilot rail, onboarding coach,
AI Center) can adopt this entry-point incrementally without touching their
existing ``services.ai_helpers`` calls.

Tenant-safety:
  The bridge applies the 3-layer visibility gate before returning context.
  Platform-only / cross-audience workflows return ``data_defaulter=True``,
  so the AI never receives a workflow_key it shouldn't see.
"""
from __future__ import annotations

from typing import Any, Optional


def invoke_with_workflow_context(
    *,
    request: Any,
    task_type: Any,
    prompt: str,
    workflow_key: Optional[str] = None,
    user_query: str = "",
    metadata: Optional[dict[str, Any]] = None,
    response_schema: Optional[str] = None,
    require_available: bool = True,
) -> Optional[tuple[Any, dict[str, Any]]]:
    """Workflow-aware variant of ``services.ai_helpers.invoke_with_request``.

    Parameters mirror ``invoke_with_request`` plus an optional
    ``workflow_key``. When ``workflow_key`` is supplied and resolves to a
    visible workflow, the registry's structured context is merged into
    ``metadata`` under the ``workflow`` key. Downstream prompts can read
    ``metadata["workflow"]`` to ground their response (route-aware, audience-
    aware, tenant-safe).

    Returns ``None`` when the underlying ``invoke_with_request`` returns
    ``None`` (AI policy disables the call) or when the gateway propagates an
    exception (logged at DEBUG by ``ai_helpers``).
    """
    # Lazy imports so this module stays a leaf in the dependency graph and
    # the AI gateway boundary scanner sees zero direct imports.
    from apps.platform_runtime.ai_workflow_bridge import (  # noqa: WPS433
        bind_workflow_context_for_ai,
    )
    from services.ai_helpers import invoke_with_request  # noqa: WPS433

    workflow_ctx = bind_workflow_context_for_ai(request=request, workflow_key=workflow_key)
    md: dict[str, Any] = dict(metadata or {})
    # Only attach workflow context when the bridge resolved a visible workflow.
    # DATA DEFAULTER state (no workflow) leaves metadata unchanged.
    if not workflow_ctx.get("data_defaulter", True):
        md["workflow"] = {
            "key": workflow_ctx["workflow_key"],
            "title": workflow_ctx["workflow_title"],
            "audience": workflow_ctx["audience"],
            "module": workflow_ctx["module"],
            "route": workflow_ctx["route"],
            "ai_context_key": workflow_ctx["ai_context_key"],
            "host_kind": workflow_ctx["host_kind"],
        }
    return invoke_with_request(
        task_type=task_type,
        prompt=prompt,
        request=request,
        user_query=user_query,
        metadata=md,
        response_schema=response_schema,
        require_available=require_available,
    )


def build_workflow_aware_metadata(
    *,
    request: Any,
    workflow_key: Optional[str] = None,
    base_metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Lower-level helper for callers that build their own gateway calls.

    Returns a metadata dict augmented with the workflow context (when the
    bridge resolves a visible workflow). Use this when an existing caller
    already does its own ``invoke_with_request`` and just wants the
    workflow-context shape merged into its metadata.
    """
    from apps.platform_runtime.ai_workflow_bridge import (  # noqa: WPS433
        bind_workflow_context_for_ai,
    )

    md: dict[str, Any] = dict(base_metadata or {})
    workflow_ctx = bind_workflow_context_for_ai(request=request, workflow_key=workflow_key)
    if not workflow_ctx.get("data_defaulter", True):
        md["workflow"] = {
            "key": workflow_ctx["workflow_key"],
            "title": workflow_ctx["workflow_title"],
            "audience": workflow_ctx["audience"],
            "module": workflow_ctx["module"],
            "route": workflow_ctx["route"],
            "ai_context_key": workflow_ctx["ai_context_key"],
            "host_kind": workflow_ctx["host_kind"],
        }
    return md


__all__ = [
    "invoke_with_workflow_context",
    "build_workflow_aware_metadata",
]
