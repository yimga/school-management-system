"""
Runtime registry for marketplace ``workflow_hooks`` manifest entries (Linux pillar).

Maps publisher-declared hook names + event types to platform trigger keys so
install-time manifests affect automation without in-process third-party code.
"""

from __future__ import annotations

from typing import Any

from apps.automation.domain_event_bridge import resolve_trigger_key
from apps.automation.trigger_dispatcher import fire


def _hooks_from_manifest(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict):
        return []
    out: list[dict[str, Any]] = []
    for key in ("extension_hooks", "extensions"):
        items = manifest.get(key)
        if isinstance(items, list):
            out.extend(i for i in items if isinstance(i, dict))
    for single_key in ("extension_hook", "extension"):
        item = manifest.get(single_key)
        if isinstance(item, dict):
            out.append(item)
    return out


def workflow_hooks_for_event_type(
    school: Any, event_type: str
) -> list[dict[str, Any]]:
    """Active sandbox/active installs whose workflow_hooks listen for ``event_type``."""
    from apps.marketplace.models import AppInstallation

    et = (event_type or "").strip()
    if not et or school is None:
        return []
    matched: list[dict[str, Any]] = []
    from apps.marketplace.models import AppInstallation as _AppInstallation

    installs = AppInstallation.objects.filter(
        school=school,
        status=_AppInstallation.Status.ACTIVE,
        uninstalled_at__isnull=True,
    ).select_related("app")
    for inst in installs:
        manifest = getattr(inst.app, "manifest", None) or {}
        for hook in _hooks_from_manifest(manifest):
            if hook.get("extension_point") != "workflow_hooks":
                continue
            event_types = hook.get("event_types") or []
            if not isinstance(event_types, list):
                continue
            if et in event_types or "*" in event_types:
                matched.append(
                    {
                        "hook_name": hook.get("hook_name", ""),
                        "app_slug": getattr(inst.app, "slug", ""),
                        "installation_id": str(inst.pk),
                    }
                )
    return matched


def fire_manifest_workflow_hooks(
    school: Any,
    event_type: str,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    After platform triggers run, invoke manifest-registered workflow hooks.

    Each hook re-dispatches via ``trigger_dispatcher.fire`` when ``event_type``
    resolves to a catalog trigger key.
    """
    results: list[dict[str, Any]] = []
    trigger_key = resolve_trigger_key(event_type)
    if not trigger_key:
        return results

    hooks = workflow_hooks_for_event_type(school, event_type)
    if not hooks:
        return results

    ctx = dict(context or {})
    ctx["_manifest_workflow_hooks"] = hooks
    # ``trigger_dispatcher.fire`` is ``fire(trigger_key, payload, *, school=None,
    # actor=None)`` — ``payload`` is POSITIONAL and there is no ``context`` kwarg.
    # Calling it as ``fire(key, school=..., context=...)`` raised TypeError on every
    # invocation; the only production caller
    # (``automation.domain_event_bridge.dispatch_domain_event_to_triggers``) swallows
    # it with ``except Exception``, so manifest workflow hooks silently never ran.
    # The existing unit test patches ``fire``, so the mock accepted the bad call.
    results.extend(fire(trigger_key, ctx, school=school))
    return results


__all__ = [
    "fire_manifest_workflow_hooks",
    "workflow_hooks_for_event_type",
]
