"""Template-tag library for the Phase 3 workflow-guidance scaffolding.

Surfaces ``workflow_registry`` + ``workflow_guidance`` to Django templates so
Phase 4 wiring can include the four scaffolded components without changing
view code. Every helper is a no-op when the workflow key is unknown OR the
visibility gate blocks the audience — components render nothing in those
cases, so adding ``{% load workflow_guidance_tags %}`` plus an include is
always safe.

Public surface:
  ``{% load workflow_guidance_tags %}``
  ``{% workflow_resolve "studio-os-output" as wf %}``
  ``{% if wf %}{% workflow_visible request wf as is_visible %}{% endif %}``
  ``{{ wf|workflow_status_payload:request }}``
  ``{{ wf|workflow_next_action_payload:request }}``
  ``{{ wf|workflow_help_panel_payload:request }}``
  ``{{ wf|workflow_tag_payloads:request }}``
"""
from __future__ import annotations

from typing import Any, Optional

from django import template

from apps.platform_runtime.workflow_guidance import (
    get_workflow,
    help_panel_for,
    is_visible_for,
    next_action_for,
    resolve_workflow_for_route,
    tags_for,
)
from apps.platform_runtime.workflow_registry import WorkflowDefinition

register = template.Library()


@register.simple_tag(name="workflow_resolve")
def workflow_resolve(key: Optional[str] = None) -> Optional[WorkflowDefinition]:
    """Resolve a workflow by explicit key.

    Use the ``as`` syntax: ``{% workflow_resolve "studio-os-output" as wf %}``.
    """
    if not key:
        return None
    return get_workflow(key)


@register.simple_tag(name="workflow_resolve_for_request", takes_context=True)
def workflow_resolve_for_request(context) -> Optional[WorkflowDefinition]:
    """Resolve a workflow whose ``route`` matches the request's URL name."""
    request = context.get("request") if context else None
    return resolve_workflow_for_route(request)


@register.simple_tag(name="workflow_visible")
def workflow_visible(request: Any, workflow: Optional[WorkflowDefinition]) -> bool:
    """Return True when the workflow passes the 3-layer visibility gate."""
    if workflow is None:
        return False
    return is_visible_for(request, workflow)


@register.filter(name="workflow_status_payload")
def workflow_status_payload(workflow: Optional[WorkflowDefinition], request: Any) -> Optional[dict]:
    """Return the status-strip context dict for the workflow, or None.

    The returned dict matches the caller contract on
    ``templates/components/workflow_status_strip.html``: ``workflow_title``,
    ``current_step``, ``step_index``, ``step_total``, ``completion``, ``owner``,
    and ``tags``.
    """
    if workflow is None or not is_visible_for(request, workflow):
        return None
    steps = list(workflow.steps or ())
    return {
        "workflow_title": workflow.title,
        "current_step": steps[0].title if steps else "",
        "step_index": 1 if steps else None,
        "step_total": len(steps) if steps else None,
        "completion": "in-progress" if steps else "not-started",
        "owner": {"label": workflow.module.rstrip("/").split("/")[-1], "kind": "system"},
        "tags": tags_for(request, workflow),
    }


@register.filter(name="workflow_next_action_payload")
def workflow_next_action_payload(workflow: Optional[WorkflowDefinition], request: Any) -> Optional[dict]:
    """Return the next-action context dict for the workflow, or None."""
    if workflow is None or not is_visible_for(request, workflow):
        return None
    return next_action_for(request, workflow)


@register.filter(name="workflow_help_panel_payload")
def workflow_help_panel_payload(workflow: Optional[WorkflowDefinition], request: Any) -> Optional[dict]:
    """Return the help-panel context dict for the workflow, or None."""
    if workflow is None or not is_visible_for(request, workflow):
        return None
    return help_panel_for(request, workflow)


@register.filter(name="workflow_tag_payloads")
def workflow_tag_payloads(workflow: Optional[WorkflowDefinition], request: Any) -> list[dict]:
    """Return the list of tag chip dicts for the workflow, or empty list."""
    if workflow is None or not is_visible_for(request, workflow):
        return []
    return tags_for(request, workflow)
