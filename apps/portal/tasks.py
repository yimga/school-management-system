"""
Portal Celery tasks: heavy AI (async) for bulk or long-running inference.
Single-turn copilot uses sync generate_ai_response; bulk support suggestion, syllabus sync, report-card remarks use async.
§2.4 Structured logging: async AI failures logged with school_id/task_id for audit.
"""
from typing import Any

from celery import shared_task
from django.core.cache import cache

from apps.platform_runtime.structured_logging import log_exception_with_context

# TTL for async AI result in cache (seconds)
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
    Heavy AI: run inference via OllamaInferenceService and store result in cache for UI poll.
    Call from bulk support suggestion, report-card remarks, or long-running flows.
    Result key: ai:async_result:{task_id}. Poll with task_id from AsyncResult.id.
    """
    from services.ai_gateway import invoke
    from apps.schools.models import School

    school = School.objects.filter(pk=school_id).first()
    task_id = self.request.id
    result_key = f"ai:async_result:{task_id}"

    def store_result(status: str, text: str | None = None, meta: dict | None = None, error: str | None = None):
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
            metadata={"school": school, "school_id": school_id, "country_code": country_code},
        )
        text = result if isinstance(result, str) else (str(result) if result is not None else None)
        if text is not None:
            store_result("done", text=text, meta=meta)
            return {"status": "done", "task_id": task_id, "text": text, "meta": meta}
        store_result("error", meta=meta, error=meta.get("error", "unavailable"))
        return {"status": "error", "task_id": task_id, "meta": meta}
    except (OSError, ConnectionError, TimeoutError, ValueError, TypeError, ImportError, AttributeError, KeyError, RuntimeError) as e:
        log_exception_with_context(
            "portal.generate_ai_response_async failed",
            school_id=school_id,
            exc_info=True,
            extra={"task_id": task_id, "prompt_key": prompt_key, "error": str(e)},
        )
        store_result("error", error=str(e))
        return {"status": "error", "task_id": task_id, "error": str(e)}
