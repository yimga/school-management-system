"""
Portal Celery tasks: heavy AI (async) for bulk or long-running inference.
Single-turn copilot uses sync generate_ai_response; bulk support suggestion, syllabus sync, report-card remarks use async.
"""
from typing import Any

from celery import shared_task
from django.core.cache import cache

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
    from services.inference import OllamaInferenceService
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
        text, meta = OllamaInferenceService.infer(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            school=school,
            country_code=country_code,
        )
        if text is not None:
            store_result("done", text=text, meta=meta)
            return {"status": "done", "task_id": task_id, "text": text, "meta": meta}
        store_result("error", meta=meta, error=meta.get("error", "unavailable"))
        return {"status": "error", "task_id": task_id, "meta": meta}
    except Exception as e:
        store_result("error", error=str(e))
        return {"status": "error", "task_id": task_id, "error": str(e)}
