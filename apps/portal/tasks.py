"""
Portal Celery tasks: heavy AI (async) for bulk or long-running inference.
Tier 4: celery_task_* via global Celery signals (config.celery).
"""

from typing import Any

from celery import shared_task
from django.core.cache import cache

from apps.platform_runtime.structured_logging import log_exception_with_context

AI_ASYNC_RESULT_TTL = 600


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
    Heavy AI: Celery worker calls ``services.ai_gateway.invoke("narrative", ...)``; result in cache for UI poll.
    Result key: ai:async_result:{task_id}. Poll with task_id from AsyncResult.id.
    """
    from services.ai_gateway import invoke
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
        result, meta = invoke(
            "narrative",
            prompt,
            user_query=user_prompt,
            metadata={
                "school": school,
                "school_id": school_id,
                "country_code": country_code,
            },
        )
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
