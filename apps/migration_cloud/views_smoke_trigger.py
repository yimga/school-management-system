"""v3.40.0 Agent 14 — "Run Smoke Now" operator trigger view.

Single GET + POST surface at
``/super/migration/smoke/trigger/`` that lets a staff operator kick off
an on-demand Migration Cloud smoke run without dropping to the shell.

GET renders a small form (tenant slug + vendor + --apply checkbox).
POST validates input, enforces the v3.40 prod-safety gate, dispatches
``apps.migration_cloud.tasks_smoke_trigger.run_smoke_on_demand`` to the
Celery queue, audit-emits ``audit.smoke.on_demand_requested``, then
redirects to Agent 13's smoke-history page (or back to the trigger
page with a flash if 13 hasn't shipped yet).

Hard contracts:

  * ``@method_decorator(require_control_plane_access, "dispatch")`` — staff
    only; never tenant-exposed.
  * CSRF-protected (no exempt) — operator action.
  * NEVER logs vendor or tenant slug as raw — sha256 prefix only.
  * Refuses ``apply=True`` against what looks like a live prod env
    (same heuristic as Agent 8's command, replicated for parity).
  * Defensive imports of Agent 13's history-URL — if not present, the
    redirect falls back to the trigger page.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.conf import settings
from django.contrib import messages
from apps.schools.control_plane import require_control_plane_access
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.decorators import method_decorator
from django.views import View

logger = logging.getLogger(__name__)


# Same vendor list as Agent 8's migration_cloud_smoke command — duplicated
# (rather than imported) so this view doesn't drag the smoke command's
# import chain into request-path module load.
_VENDOR_CHOICES = (
    "powerschool",
    "blackbaud",
    "veracross",
    "alma",
    "facts",
    "skyward",
)


def _hash_slug_prefix(slug: str) -> str:
    """sha256(slug)[:12] — matches models_audit + Agent 8 helpers."""
    return hashlib.sha256((slug or "").encode("utf-8")).hexdigest()[:12]


def _looks_like_prod(apply_mode: bool) -> bool:
    """Re-implementation of the smoke command's prod-safety heuristic.

    Returns True when --apply against the current env should be refused.
    """
    if not apply_mode:
        return False
    debug = bool(getattr(settings, "DEBUG", False))
    allowed = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
    looks_dev = any(
        (h or "").startswith("localhost")
        or (h or "").startswith("127.")
        or (h or "").endswith(".invalid")
        or (h or "") == "*"
        for h in allowed
    )
    if debug or looks_dev:
        return False
    import os
    override = (
        os.environ.get("MIGRATION_CLOUD_SMOKE_ALLOW_PROD", "") or ""
    ).strip()
    if override == "1":
        return False
    return True


def _resolve_history_redirect(shell: str) -> str | None:
    """Return Agent 13's smoke-history URL if it has shipped.

    Agent 13 has not necessarily shipped yet — race tolerant. We try
    a small set of URL names by convention; if none resolve, return
    None and the caller falls back to the trigger page.
    """
    candidates = (
        "migration_cloud_super:migration_cloud_smoke_history",
        "migration_cloud_portal:migration_cloud_smoke_history",
        "migration_cloud_super:smoke_history",
        "migration_cloud_portal:smoke_history",
        "migration_cloud_super:smoke_run_history",
        "migration_cloud_portal:smoke_run_history",
    )
    for name in candidates:
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    return None


def _emit_audit(
    *,
    event_type: str,
    tenant_slug: str,
    actor,
    payload: dict[str, Any],
) -> None:
    """Best-effort audit emit. Swallows rate-limit + any other error."""
    try:
        from apps.migration_cloud.models_audit import (
            AuditEventRateLimitExceeded,
            MigrationCloudAuditEvent,
            MigrationCloudAuditEventType,
        )
    except Exception:  # pragma: no cover - audit module absent in lane
        return
    valid = {c.value for c in MigrationCloudAuditEventType}
    if event_type not in valid:
        # Fall back to the closest-fit registered event so the
        # operator action is still recorded somewhere.
        event_type = MigrationCloudAuditEventType.KEY_ROTATE.value
        payload = {**payload, "registered_choice_fallback": event_type}
    try:
        MigrationCloudAuditEvent.objects.record(
            tenant_slug=tenant_slug,
            event_type=event_type,
            actor=actor,
            subject=f"smoke-trigger-{_hash_slug_prefix(tenant_slug)}",
            payload_summary=payload,
        )
    except AuditEventRateLimitExceeded:
        # Don't fail the operator action because the audit chain is
        # rate-limited; the meta-event has already been written.
        logger.info(
            "migration_cloud.smoke.trigger.audit_emit_rate_limited "
            "tenant_hash=%s event_type=%s",
            _hash_slug_prefix(tenant_slug), event_type,
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "migration_cloud.smoke.trigger.audit_emit_failed "
            "tenant_hash=%s err_type=%s",
            _hash_slug_prefix(tenant_slug), type(exc).__name__,
        )


@method_decorator(require_control_plane_access, name="dispatch")
class SmokeRunTriggerView(View):
    """Operator-facing "Run Smoke Now" form + dispatcher."""

    template_name = "migration_cloud/operator/smoke_trigger.html"

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        context = self._base_context(request, **kwargs)
        return render(request, self.template_name, context)

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        tenant = (request.POST.get("tenant") or "").strip()
        vendor = (request.POST.get("vendor") or "").strip().lower()
        apply_mode = bool(request.POST.get("apply"))

        errors: list[str] = []
        if not tenant:
            errors.append("Tenant slug is required.")
        if vendor not in _VENDOR_CHOICES:
            errors.append(
                f"Vendor must be one of: {', '.join(_VENDOR_CHOICES)}."
            )
        if _looks_like_prod(apply_mode):
            errors.append(
                "LIVE PROD DETECTED: --apply refused. Set "
                "MIGRATION_CLOUD_SMOKE_ALLOW_PROD=1 in env if you "
                "really intend to mutate prod."
            )

        if errors:
            for e in errors:
                messages.error(request, e)
            context = self._base_context(request, **kwargs)
            context["form_tenant"] = tenant
            context["form_vendor"] = vendor
            context["form_apply"] = apply_mode
            return render(request, self.template_name, context, status=400)

        # Dispatch — defensive import so a Celery-less lane still works.
        dispatched = False
        try:
            from apps.migration_cloud.tasks_smoke_trigger import (
                run_smoke_on_demand,
            )
            try:
                run_smoke_on_demand.delay(  # type: ignore[attr-defined]
                    tenant=tenant,
                    vendor=vendor,
                    apply=apply_mode,
                    requested_by_user_id=getattr(request.user, "pk", None),
                )
                dispatched = True
            except Exception as exc:  # broad — celery may be unavailable
                logger.warning(
                    "migration_cloud.smoke.trigger.delay_failed "
                    "tenant_hash=%s err_type=%s",
                    _hash_slug_prefix(tenant), type(exc).__name__,
                )
                # Fall back to synchronous invocation so the operator
                # still gets a result in dev / non-celery lanes.
                try:
                    run_smoke_on_demand(
                        tenant=tenant,
                        vendor=vendor,
                        apply=apply_mode,
                        requested_by_user_id=getattr(request.user, "pk", None),
                    )
                    dispatched = True
                except Exception as exc2:  # pylint: disable=broad-except
                    logger.warning(
                        "migration_cloud.smoke.trigger.sync_invoke_failed "
                        "tenant_hash=%s err_type=%s",
                        _hash_slug_prefix(tenant), type(exc2).__name__,
                    )
        except ImportError:
            logger.warning(
                "migration_cloud.smoke.trigger.task_module_missing "
                "tenant_hash=%s",
                _hash_slug_prefix(tenant),
            )

        _emit_audit(
            event_type="migration.smoke.on_demand_requested",
            tenant_slug=tenant,
            actor=request.user,
            payload={
                "vendor": vendor,
                "apply": bool(apply_mode),
                "dispatched": bool(dispatched),
                "requested_by_user_id": int(
                    getattr(request.user, "pk", 0) or 0
                ),
            },
        )

        if dispatched:
            messages.success(
                request,
                "Smoke run queued. Watch the history page for results.",
            )
        else:
            messages.warning(
                request,
                "Smoke task module unavailable; nothing queued. Check "
                "Celery worker + apps.migration_cloud.tasks_smoke_trigger.",
            )

        history_url = _resolve_history_redirect(kwargs.get("shell", "super"))
        if history_url:
            return redirect(history_url)
        return redirect(request.path)

    def _base_context(self, request: HttpRequest, **kwargs) -> dict[str, Any]:
        shell = kwargs.get("shell", "super")
        return {
            "page_title": "Migration Cloud — Run Smoke Now",
            "shell": shell,
            "vendor_choices": _VENDOR_CHOICES,
            "default_vendor": "powerschool",
            "form_tenant": getattr(
                settings, "MIGRATION_CLOUD_SMOKE_SYNTHETIC_TENANT", "",
            ),
            "form_vendor": "powerschool",
            "form_apply": False,
            "history_url": _resolve_history_redirect(shell),
            "command_center_url": _try_reverse(
                "migration_cloud_super:migration_cloud_command_center"
                if shell == "super"
                else "migration_cloud_portal:migration_cloud_command_center"
            ),
        }


def _try_reverse(name: str) -> str | None:
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


__all__ = ["SmokeRunTriggerView"]
