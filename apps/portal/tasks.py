"""
Portal Celery tasks: heavy AI (async) for bulk or long-running inference.
Tier 4: celery_task_* via global Celery signals (config.celery).
"""

from typing import Any

from celery import shared_task
from django.core.cache import cache

from apps.platform_runtime.structured_logging import log_exception_with_context

AI_ASYNC_RESULT_TTL = 600


def _normalize_async_gateway_metadata(
    school,
    school_id,
    country_code: str | None,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    from services.ai_helpers import normalize_gateway_metadata

    return normalize_gateway_metadata(
        {
            "school": school,
            "school_id": school_id,
            "tenant_id": kwargs.get("tenant_id") or school_id,
            "country_code": country_code,
            "user_id": kwargs.get("user_id"),
            "role": kwargs.get("role"),
        }
    )


@shared_task(name="portal.generate_ai_response_async", bind=True)
def generate_ai_response_async(
    self,
    school_id: int,
    prompt_key: str,
    user_prompt: str,
    system_prompt: str = "",
    country_code: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Heavy AI: Celery worker calls ``services.ai_helpers.invoke_with_request`` (RBAC guard + gateway); result in cache for UI poll.
    Result key: ai:async_result:{task_id}. Poll with task_id from AsyncResult.id.
    """
    from services.ai_helpers import invoke_with_request
    from apps.schools.models import School

    school = School.objects.filter(pk=school_id).first()
    task_id = self.request.id
    result_key = f"ai:async_result:{task_id}"

    def store_result(
        status: str,
        text: str | None = None,
        meta: dict | None = None,
        error: str | None = None,
    ):
        cache.set(
            result_key,
            {"status": status, "text": text, "meta": meta or {}, "error": error},
            timeout=AI_ASYNC_RESULT_TTL,
        )

    store_result("running")
    try:
        prompt = (system_prompt + "\n\n" + user_prompt).strip() or user_prompt
        outcome = invoke_with_request(
            task_type="narrative",
            prompt=prompt,
            school=school,
            user_query=user_prompt,
            metadata=_normalize_async_gateway_metadata(
                school, school_id, country_code, kwargs
            ),
        )
        if outcome is None:
            store_result("error", error="unavailable")
            return {"status": "error", "task_id": task_id, "error": "unavailable"}
        result, meta = outcome
        text = (
            result
            if isinstance(result, str)
            else (str(result) if result is not None else None)
        )
        if text is not None:
            store_result("done", text=text, meta=meta)
            return {"status": "done", "task_id": task_id, "text": text, "meta": meta}
        store_result("error", meta=meta, error=meta.get("error", "unavailable"))
        return {"status": "error", "task_id": task_id, "meta": meta}
    except (
        OSError,
        ConnectionError,
        TimeoutError,
        ValueError,
        TypeError,
        ImportError,
        AttributeError,
        KeyError,
        RuntimeError,
    ) as e:
        log_exception_with_context(
            "portal.generate_ai_response_async failed",
            school_id=school_id,
            exc_info=True,
            extra={"task_id": task_id, "prompt_key": prompt_key, "error": str(e)},
        )
        store_result("error", error=str(e))
        return {"status": "error", "task_id": task_id, "error": str(e)}


@shared_task(name="portal.apply_support_ticket_ai_triage")
def apply_support_ticket_ai_triage(ticket_id: str) -> dict[str, Any]:
    """
    Load a GlobalSupportTicket (public/shared schema), run ``support_suggest`` with KB context,
    and persist suggestions under ``metadata["ai_triage"]`` without changing human-set priority.
    """
    import uuid

    from django.db import connection
    from django.utils import timezone

    try:
        tid = uuid.UUID(str(ticket_id))
    except (ValueError, TypeError, AttributeError):
        return {"ok": False, "error": "invalid_ticket_id"}

    from apps.portal.ai_provider import suggest_support_ticket_response
    from apps.siteconfig.models_feature_controls import GlobalSupportTicket

    def _run() -> dict[str, Any]:
        ticket = (
            GlobalSupportTicket.objects.select_related("school")
            .filter(pk=tid)
            .first()
        )
        if ticket is None:
            return {"ok": False, "error": "not_found"}
        md = dict(ticket.metadata or {})
        cc = (md.get("country_code") or "")[:2] or None
        suggestions, meta = suggest_support_ticket_response(
            ticket.subject,
            ticket.body,
            country_code=cc,
            school=ticket.school,
            user_id=getattr(ticket, "user_id", None),
            role=(
                getattr(getattr(ticket, "user", None), "role", None)
                or getattr(getattr(ticket, "user", None), "portal_role", None)
                or getattr(getattr(ticket, "user", None), "user_type", None)
            ),
        )
        preview = None
        if isinstance(suggestions, dict):
            sr = suggestions.get("suggested_reply")
            if isinstance(sr, str):
                preview = sr[:500]
        md["ai_triage"] = {
            "at": timezone.now().isoformat(),
            "suggestions": suggestions,
            "gateway": meta,
            "suggested_reply_preview": preview,
        }
        # tenant-isolation-allow: GlobalSupportTicket lives in the public schema (see schema_context wrap below); pk filter is globally-unique
        GlobalSupportTicket.objects.filter(pk=tid).update(metadata=md)
        return {"ok": True, "ticket_id": str(tid)}

    schema_name = getattr(connection, "schema_name", None)
    if schema_name and schema_name != "public":
        try:
            from django_tenants.utils import schema_context

            with schema_context("public"):
                return _run()
        except ImportError:
            pass
    return _run()


def _fan_out_per_school(task_name: str, runnable) -> dict[str, Any]:
    """Run ``runnable`` once per active school, inside that school's tenant context.

    ``apps.portal`` (and ``apps.feedback``) are TENANT_APPS-only, so a beat worker
    -- a plain ``celery -A config worker`` -- has its connection on ``public``,
    where ``portal_kbarticle`` / ``feedback_*`` do not exist. An unscoped task
    body therefore fails on every tenant. Same convention as
    apps/people/tasks.py: iterate active schools and enter tenant context per id.

    One bad tenant must not skip the rest, so failures are collected and logged
    per school; the last one is re-raised at the end so a schema/connection
    failure is visible to Celery instead of being folded into a return value
    that nothing inspects.
    """
    from apps.schools.celery_tasks import (
        _run_with_tenant_context,
        get_active_school_ids,
    )

    school_ids = get_active_school_ids()
    failures: list[str] = []
    last_exc: BaseException | None = None
    for sid in school_ids:
        try:
            _run_with_tenant_context(school_id=sid, runnable=runnable)
        except Exception as exc:  # noqa: BLE001 — isolate one tenant, report at end
            failures.append(str(sid))
            last_exc = exc
            log_exception_with_context(
                f"{task_name} failed for school",
                school_id=str(sid),
                exc_info=True,
                extra={"error": str(exc)},
            )
    if last_exc is not None:
        raise last_exc
    return {"ok": True, "schools": len(school_ids), "failed": failures}


@shared_task(name="portal.reindex_kb_help_embeddings_weekly")
def reindex_kb_help_embeddings_weekly(limit: int = 0) -> dict[str, Any]:
    """Weekly KB embedding refresh (batch 1341). No-op when Ollama unavailable."""

    def _run() -> None:
        from django.core.management import call_command

        call_command("reindex_kb_help_embeddings", limit=limit or 0)

    return _fan_out_per_school("portal.reindex_kb_help_embeddings_weekly", _run)


@shared_task(name="portal.build_code_support_index_weekly")
def build_code_support_index_weekly() -> dict[str, Any]:
    """Refresh operator code-support index (batch 1341)."""
    from django.core.management import call_command

    try:
        call_command("build_code_support_index")
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@shared_task(name="portal.purge_help_telemetry_monthly")
def purge_help_telemetry_monthly() -> dict[str, Any]:
    """Purge aged help telemetry (batch 1354). Reads feedback_* (tenant) tables."""

    def _run() -> None:
        from django.core.management import call_command

        call_command("purge_help_telemetry", apply=True)

    return _fan_out_per_school("portal.purge_help_telemetry_monthly", _run)


@shared_task(name="portal.help_north_star_weekly_email")
def help_north_star_weekly_email(days: int = 7) -> dict[str, Any]:
    """Weekly north-star CSV/PDF email to operator distro (batch 1356)."""
    try:
        from apps.portal.help_north_star_report import send_north_star_weekly_email

        return send_north_star_weekly_email(days=days)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@shared_task(name="portal.notify_forum_reply")
def notify_forum_reply_task(
    reply_id: int, topic_url: str = "", school_id: Any = None
) -> dict[str, Any]:
    """Email topic followers when a new forum reply is posted (batch 1360).

    ``school_id`` is required in production: ``portal_communityforumreply`` is a
    tenant table and the worker's connection defaults to ``public``, so the
    lookup has to run inside the reply's own tenant context. It stays optional
    only so an already-queued payload from before this change still runs (eager
    mode, where the caller's schema is already active).
    """

    def _run() -> dict[str, Any]:
        from apps.portal.forum_notifications import send_forum_reply_notifications

        return send_forum_reply_notifications(reply_id, topic_url=topic_url)

    try:
        if school_id is None:
            return _run()
        from apps.schools.celery_tasks import _run_with_tenant_context

        return _run_with_tenant_context(school_id=school_id, runnable=_run)
    except Exception as exc:
        log_exception_with_context(
            "portal.notify_forum_reply failed",
            route=f"forum_reply:{reply_id}",
        )
        return {"sent": 0, "skipped": 0, "errors": 1, "error": str(exc)}


@shared_task(name="portal.archive_stale_kb_articles_monthly")
def archive_stale_kb_articles_monthly(limit: int = 50) -> dict[str, Any]:
    """Auto-archive unhelpful published KB articles (batch 1356)."""
    results: list[dict[str, Any]] = []

    def _run() -> None:
        from apps.portal.kb_archive import (
            archive_kb_articles,
            stale_kb_archive_candidates,
        )

        candidates = stale_kb_archive_candidates(limit=limit)
        results.append(archive_kb_articles(candidates, dry_run=False))

    outcome = _fan_out_per_school("portal.archive_stale_kb_articles_monthly", _run)
    return {**outcome, "results": results}
