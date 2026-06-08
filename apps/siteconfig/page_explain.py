"""
Page explain context — workflow tags, route help, and field manifests for shells.
"""

from __future__ import annotations

import json
from typing import Any

from apps.siteconfig.ui_field_help import UI_FIELD_HELP, _ensure_platform_catalog
from apps.siteconfig.ui_route_help import entity_prefix_for_request, resolve_route_help


def _workflow_context(request: Any) -> tuple[Any, list[dict[str, Any]]]:
    from apps.platform_runtime.workflow_guidance import (
        is_visible_for,
        resolve_workflow_for_route,
        tags_for,
    )

    workflow = resolve_workflow_for_route(request)
    if workflow is None or not is_visible_for(request, workflow):
        return None, []
    return workflow, tags_for(request, workflow)


def _role_entity_prefixes(request: Any) -> tuple[str, ...]:
    user = getattr(request, "user", None)
    role = getattr(user, "role", None) or ""
    role_upper = str(role).upper()
    mapping = {
        "TEACHER": ("teacher",),
        "PARENT": ("parent",),
        "STUDENT": ("student",),
    }
    return mapping.get(role_upper, ())


def build_field_manifest(request: Any, route_help: dict[str, Any]) -> list[dict[str, str]]:
    """
    Inputs the auto-tag script may wire on this page.

    Each item: {entity, field, names[]} where names are HTML name/id candidates.
    """
    _ensure_platform_catalog()
    prefix = entity_prefix_for_request(request)
    host = getattr(request, "public_host_kind", None)
    entity_scopes: set[str] = {prefix, "common"}
    entity_scopes.update(_role_entity_prefixes(request))
    if host == "manager":
        entity_scopes.add("super")
        entity_scopes.add("operator")
    if prefix == "migration_cloud":
        entity_scopes.add("canonical")
        entity_scopes.add("migration")

    seen: set[str] = set()
    manifest: list[dict[str, str]] = []

    def _add(entity: str, field: str, names: tuple[str, ...]) -> None:
        key = f"{entity}.{field}"
        if key not in UI_FIELD_HELP or key in seen:
            return
        seen.add(key)
        manifest.append(
            {
                "entity": entity,
                "field": field,
                "names": json.dumps(list(names)),
            }
        )

    for route_field in route_help.get("fields") or ():
        if not isinstance(route_field, str):
            continue
        _add(prefix, route_field, (route_field, f"id_{route_field}"))

    for key in UI_FIELD_HELP:
        if "." not in key:
            continue
        entity, field = key.split(".", 1)
        if entity == "canonical":
            if "canonical" not in entity_scopes:
                continue
            # canonical.{domain}.{header} — wire header name on migration forms
            parts = field.split(".", 1)
            if len(parts) == 2:
                wire_name = parts[1]
                _add(entity, field, (wire_name, wire_name.replace("_", "-")))
            continue
        if entity in entity_scopes:
            _add(entity, field, (field, f"id_{field}"))

    return manifest


def build_page_explain_context(request: Any) -> dict[str, Any]:
    """Context dict for ``page_explain_context`` processor and templates."""
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return {}

    route_help = resolve_route_help(request)
    workflow, workflow_tags = _workflow_context(request)
    manifest = build_field_manifest(request, route_help)

    show_strip = bool(
        route_help.get("title")
        or route_help.get("body")
        or workflow_tags
        or manifest
    )

    return {
        "rmc_page_help": route_help,
        "rmc_page_workflow": workflow,
        "rmc_page_workflow_tags": workflow_tags,
        "rmc_page_field_manifest": manifest,
        "rmc_page_explain_enabled": show_strip,
    }
