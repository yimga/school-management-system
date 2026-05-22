"""
AI Gateway productized endpoints: setup assistant, workflow draft, policy explain,
document classify, semantic search, migration suggest. All go through services.ai_gateway;
permissions and audit applied; no direct provider access from frontend.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, IntegrityError
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from apps.compliance.models import AuditLog
from apps.platform_runtime.structured_logging import log_view_exception
from apps.portal.views_ai_copilot import _check_rate_limit
from apps.siteconfig.prompt_registry import get_prompt_template
from services.ai_gateway import TaskType, invoke, record_feedback
from services.ai_memory import AIMemoryService, get_embedding_for_text
from services.inference import strip_pii_for_inference

logger = logging.getLogger(__name__)
OPTIONAL_GATEWAY_ERRORS = (
    AttributeError,
    DatabaseError,
    ImportError,
    TypeError,
    ValueError,
)
# Service/gateway failures (invoke, embedding, etc.) — used for view-level catch after json.JSONDecodeError
GATEWAY_VIEW_ERRORS = (
    AttributeError,
    DatabaseError,
    ImportError,
    TypeError,
    ValueError,
    OSError,
    ConnectionError,
    RuntimeError,
    KeyError,
)


# Rate limit: same as copilot (per-user sliding window)
def _gateway_rate_limit(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None
    allowed, retry_after = _check_rate_limit(user, request)
    if not allowed:
        return JsonResponse(
            {"success": False, "error": "Rate limit exceeded. Try again later."},
            status=429,
            headers={"Retry-After": str(retry_after)} if retry_after else None,
        )
    return None


def _school_id(request) -> str | None:
    school = getattr(request, "school", None)
    school_id = None
    if school is not None:
        school_id = getattr(school, "pk", None) or getattr(school, "id", None)
    return str(school_id) if school_id is not None else None


def _actor_roles(request) -> list[str]:
    user = getattr(request, "user", None)
    if not user:
        return []
    roles: set[str] = set()
    for attr in ("role", "portal_role", "user_type"):
        value = getattr(user, attr, None)
        if value:
            roles.add(str(value).strip().lower())
    try:
        for group in user.groups.all():
            name = getattr(group, "name", None)
            if name:
                roles.add(str(name).strip().lower())
    except (AttributeError, DatabaseError, TypeError):
        pass
    if getattr(user, "is_staff", False):
        roles.update({"staff", "admin"})
    if getattr(user, "is_superuser", False):
        roles.update({"superuser", "super_admin"})
    return sorted(role for role in roles if role)


def _retrieval_kwargs(request) -> dict[str, Any]:
    user = getattr(request, "user", None)
    return {
        "actor_roles": _actor_roles(request),
        "actor_is_staff": bool(user and getattr(user, "is_staff", False)),
        "actor_is_superuser": bool(user and getattr(user, "is_superuser", False)),
    }


def _search_ai_memory(
    request,
    scope: str,
    embedding: list[float],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    school_id = _school_id(request)
    return AIMemoryService.search_similar(
        school_id,
        scope,
        embedding,
        limit=limit,
        global_only=not bool(school_id),
        **_retrieval_kwargs(request),
    )


def _redact_audit_meta(meta: dict | None) -> dict:
    """Ensure no prompt/response or other sensitive content is stored in audit new_values."""
    if not meta:
        return {}
    safe = {}
    skip_keys = {"prompt", "response", "user_query", "query", "text", "content"}
    for k, v in meta.items():
        if k.lower() in skip_keys:
            safe[k] = "[redacted]"
        elif isinstance(v, dict):
            safe[k] = _redact_audit_meta(v)
        else:
            safe[k] = v
    return safe


def _gateway_permission_denied_response(meta: dict) -> JsonResponse:
    """§2.3: return 403 when get_ai_permission_for_user denied."""
    return JsonResponse(
        {"success": False, "error": meta.get("error", "Permission denied")}, status=403
    )


def _gateway_meta_error_response(
    meta: dict,
    *,
    result: Any = None,
    budget_error: str = "AI request budget exceeded.",
) -> JsonResponse | None:
    if meta.get("outcome") == "permission_denied":
        return _gateway_permission_denied_response(meta)
    if meta.get("budget_exceeded"):
        return JsonResponse(
            {"success": False, "error": budget_error, "meta": meta},
            status=429,
        )
    if meta.get("prompt_injection_blocked") or meta.get("denied"):
        return JsonResponse(
            {
                "success": False,
                "error": "Request rejected by safety policy. Please rephrase as a normal school-operation question.",
                "meta": meta,
            },
            status=400,
        )
    if meta.get("live_ai_unavailable") and isinstance(result, dict):
        return JsonResponse(
            {
                "success": False,
                "error": "live_ai_unavailable",
                "guided": {
                    "summary": result.get("summary", ""),
                    "actions": result.get("actions", []),
                    "cautions": result.get("cautions", []),
                    "references": result.get("references", []),
                },
                "meta": meta,
            },
            status=503,
        )
    if meta.get("provider") == "none":
        error_text = result if isinstance(result, str) and result.strip() else (
            meta.get("error") or "AI providers are currently unavailable and rules fallback is disabled."
        )
        return JsonResponse(
            {"success": False, "error": error_text, "meta": meta},
            status=503,
        )
    return None


def _log_gateway_audit(
    request, feature: str, task_type: str, outcome: str, meta: dict | None = None
):
    try:
        safe_meta = _redact_audit_meta(meta or {})
        AuditLog.objects.create(
            user=getattr(request, "user", None),
            ip_address=(request.META.get("REMOTE_ADDR") or "")[:45],
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:500],
            action=AuditLog.Action.VIEW,
            model_name="AIGateway",
            object_id=feature,
            object_repr=f"AI Gateway {feature}",
            app_label="portal",
            reason=task_type,
            sensitivity=AuditLog.Sensitivity.LOW,
            new_values=dict(outcome=outcome, **safe_meta),
        )
    except (DatabaseError, IntegrityError, AttributeError, TypeError, ValueError) as e:
        logger.debug("Gateway audit log failed: %s", e)


def _gateway_response(
    request,
    task_type: str,
    prompt: str,
    user_query: str = "",
    response_schema: str | None = None,
    rag_snippets: list[dict[str, Any]] | None = None,
):
    from services.ai_helpers import normalize_gateway_metadata
    from services.ai_permissions import get_ai_permission_for_user

    school = getattr(request, "school", None)
    if not get_ai_permission_for_user(request.user, task_type, school):
        return None, {
            "outcome": "permission_denied",
            "error": "AI permission denied for this task",
        }
    user_id = getattr(getattr(request, "user", None), "pk", None) or getattr(
        getattr(request, "user", None), "id", None
    )
    role = (
        getattr(getattr(request, "user", None), "role", None)
        or getattr(getattr(request, "user", None), "portal_role", None)
        or getattr(getattr(request, "user", None), "user_type", None)
    )
    country_code = getattr(school, "country_code", None) or getattr(
        getattr(school, "default_region", None),
        "code",
        None,
    )
    school_id = _school_id(request)
    md = normalize_gateway_metadata(
        {
            "request": request,
            "school": school,
            "school_id": school_id,
            "tenant_id": school_id,
            "user_id": str(user_id) if user_id is not None else None,
            "role": role,
            "country_code": country_code,
            "rag_snippets": rag_snippets or [],
        }
    )
    result, meta = invoke(
        task_type,
        prompt,
        user_query=user_query,
        metadata=md,
        response_schema=response_schema,
    )
    if (
        school
        and isinstance(meta, dict)
        and not meta.get("prompt_injection_blocked")
    ):
        try:
            from apps.marketplace.monetization import USAGE_METRIC_AI, record_usage_meter_increment

            record_usage_meter_increment(
                school=school,
                metric_code=USAGE_METRIC_AI,
                quantity=1,
                metadata={"source": "portal.views_ai_gateway", "task_type": task_type},
            )
        except OPTIONAL_GATEWAY_ERRORS:
            logger.debug("AI gateway usage meter rollup skipped", exc_info=True)
    return result, meta


def _parse_optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError("boolean field must be true/false")


# --- Setup assistant ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_setup_assistant(request):
    """POST: { "query": "..." } → config_explain / setup_recommend. Returns citations for RAG sources."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:2000]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        context_parts = []
        citations = []
        emb = get_embedding_for_text(query, max_tokens=512)
        if emb:
            for scope in ("help", "config", "default"):
                for r in _search_ai_memory(request, scope, emb, limit=2):
                    context_parts.append(str(r.get("metadata", ""))[:400])
                    citations.append(
                        {
                            "id": r.get("id"),
                            "scope": scope,
                            "metadata": {
                                k: v
                                for k, v in (r.get("metadata") or {}).items()
                                if k not in ("embedding", "raw_text")
                            },
                        }
                    )
        context = "\n".join(context_parts)[:1200] if context_parts else ""
        try:
            prompt = get_prompt_template(
                "setup_assistant", {"query": query, "context_block": context}
            )
        except OPTIONAL_GATEWAY_ERRORS:
            prompt = (
                "You are a Setup Studio assistant. Answer concisely and helpfully.\n\n"
            )
            if context:
                prompt += f"Relevant context:\n{context}\n\n"
            prompt += f"User question: {query}\n\nProvide 3–5 short actionable setup tips or explain the requested config."
        result, meta = _gateway_response(
            request, TaskType.SETUP_RECOMMEND, prompt, user_query=query
        )
        error_response = _gateway_meta_error_response(
            meta,
            result=result,
            budget_error="AI request budget exceeded for this tenant.",
        )
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "setup_assistant", "setup_recommend", "success", meta
        )
        return JsonResponse(
            {"success": True, "response": result, "citations": citations, "meta": meta}
        )
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Setup assistant failed",
            extra={"error": str(e)},
        )
        _log_gateway_audit(
            request,
            "setup_assistant",
            "setup_recommend",
            "error",
            {"error": str(e)[:200]},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Workflow draft ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_workflow_draft(request):
    """POST: { "description": "When student misses 3 days notify parent" } → workflow_draft JSON."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        description = (body.get("description") or body.get("query") or "").strip()[
            :1500
        ]
        if not description:
            return JsonResponse(
                {"success": False, "error": "description required"}, status=400
            )
        prompt = (
            get_prompt_template("workflow_draft", {"query": description}) or ""
        ).strip() or (
            f"Generate a workflow definition as JSON only. User request: {description}\n\n"
            "Respond with a single JSON object with keys: name (string), trigger_type (string), "
            "steps (array of { action, role, config }), description (string). No other text."
        )
        result, meta = _gateway_response(
            request,
            TaskType.WORKFLOW_DRAFT,
            prompt,
            user_query=description,
            response_schema="workflow_draft",
        )
        error_response = _gateway_meta_error_response(
            meta,
            result=result,
            budget_error="AI request budget exceeded for this tenant.",
        )
        if error_response:
            return error_response
        _log_gateway_audit(request, "workflow_draft", "workflow_draft", "success", meta)
        return JsonResponse(
            {
                "success": True,
                "draft": result
                if isinstance(result, dict)
                else {"description": result},
                "meta": meta,
            }
        )
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Workflow draft failed",
            extra={"error": str(e)},
        )
        _log_gateway_audit(
            request,
            "workflow_draft",
            "workflow_draft",
            "error",
            {"error": str(e)[:200]},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Policy explain ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_policy_explain(request):
    """POST: { "policy_text": "..." or "query": "..." } → policy_explain structured."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or body.get("policy_text") or "").strip()[:3000]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query or policy_text required"}, status=400
            )
        context_parts = []
        citations = []
        emb = get_embedding_for_text(query, max_tokens=512)
        if emb:
            for r in _search_ai_memory(request, "policy", emb, limit=5):
                context_parts.append(str(r.get("metadata", ""))[:400])
                citations.append(
                    {
                        "id": r.get("id"),
                        "scope": "policy",
                        "metadata": {
                            k: v
                            for k, v in (r.get("metadata") or {}).items()
                            if k not in ("embedding", "raw_text")
                        },
                    }
                )
        if not context_parts and emb:
            for r in _search_ai_memory(request, "default", emb, limit=3):
                context_parts.append(str(r.get("metadata", ""))[:400])
                citations.append(
                    {
                        "id": r.get("id"),
                        "scope": "default",
                        "metadata": {
                            k: v
                            for k, v in (r.get("metadata") or {}).items()
                            if k not in ("embedding", "raw_text")
                        },
                    }
                )
        context = "\n".join(context_parts)[:1200] if context_parts else ""
        try:
            prompt = get_prompt_template(
                "policy_explain", {"query": query, "context_block": context}
            )
        except OPTIONAL_GATEWAY_ERRORS:
            prompt = "You are a policy explainer. Explain or compare policies in plain language.\n\n"
            if context:
                prompt += f"Relevant context:\n{context}\n\n"
            prompt += (
                f"User request: {query}\n\n"
                'Respond with JSON only: { "summary": "...", "differences": [], "warnings": [] }. '
                "No other text."
            )
        result, meta = _gateway_response(
            request,
            TaskType.POLICY_EXPLAIN,
            prompt,
            user_query=query,
            response_schema="policy_explain",
        )
        error_response = _gateway_meta_error_response(
            meta,
            result=result,
            budget_error="AI request budget exceeded for this tenant.",
        )
        if error_response:
            return error_response
        _log_gateway_audit(request, "policy_explain", "policy_explain", "success", meta)
        return JsonResponse(
            {
                "success": True,
                "explanation": result
                if isinstance(result, dict)
                else {"summary": result},
                "citations": citations,
                "meta": meta,
            }
        )
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Policy explain failed",
            extra={"error": str(e)},
        )
        _log_gateway_audit(
            request,
            "policy_explain",
            "policy_explain",
            "error",
            {"error": str(e)[:200]},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Document classify ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_document_classify(request):
    """POST: { "text": "..." } → doc_classify category/tags/confidence."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        text = (body.get("text") or "").strip()[:8000]
        if not text:
            return JsonResponse(
                {"success": False, "error": "text required"}, status=400
            )
        safe_text = strip_pii_for_inference(text)
        prompt = (
            get_prompt_template("document_classify", {"query": safe_text[:2000]}) or ""
        ).strip() or (
            f'Classify this document. Respond with JSON only: {{ "category": "...", "tags": ["..."], "confidence": 0.0-1.0 }}.\n\nDocument excerpt: {safe_text[:2000]}\n\nNo other text.'
        )
        result, meta = _gateway_response(
            request,
            TaskType.DOC_CLASSIFY,
            prompt,
            user_query=text[:500],
            response_schema="doc_classify",
        )
        error_response = _gateway_meta_error_response(
            meta,
            result=result,
            budget_error="AI request budget exceeded for this tenant.",
        )
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "document_classify", "doc_classify", "success", meta
        )
        return JsonResponse(
            {
                "success": True,
                "classification": result
                if isinstance(result, dict)
                else {"category": "general"},
                "meta": meta,
            }
        )
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Document classify failed",
            extra={"error": str(e)},
        )
        _log_gateway_audit(
            request,
            "document_classify",
            "doc_classify",
            "error",
            {"error": str(e)[:200]},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Semantic search ---
@require_http_methods(["POST", "GET"])
@csrf_protect
@login_required
def api_semantic_search(request):
    """POST: { "query": "...", "scope": "..." } or GET ?query=...&scope=... → retrieval + optional summarization."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        if request.method == "GET":
            query = (request.GET.get("query") or "").strip()[:500]
            scope = (request.GET.get("scope") or "default").strip()[:64]
        else:
            body = json.loads(request.body) if request.body else {}
            query = (body.get("query") or "").strip()[:500]
            scope = (body.get("scope") or "default").strip()[:64]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        embedding = get_embedding_for_text(query, max_tokens=512)
        if not embedding:
            return JsonResponse(
                {
                    "success": True,
                    "results": [],
                    "meta": {"reason": "embedding_unavailable"},
                }
            )
        results = _search_ai_memory(request, scope, embedding, limit=10)
        # Optional: summarize top result via gateway
        if results and query:
            context = str(results[0].get("metadata", ""))[:1500]
            prompt = (
                get_prompt_template(
                    "semantic_search", {"query": query, "context_block": context}
                )
                or ""
            ).strip() or (
                f"Based on this context, answer briefly: {query}\n\nContext: {context}"
            )
            summary, meta = _gateway_response(
                request, TaskType.SEMANTIC_SEARCH, prompt, user_query=query
            )
            error_response = _gateway_meta_error_response(
                meta,
                result=summary,
                budget_error="AI request budget exceeded for this tenant.",
            )
            if error_response:
                return error_response
            _log_gateway_audit(
                request, "semantic_search", "semantic_search", "success", meta
            )
            return JsonResponse(
                {
                    "success": True,
                    "results": [{"metadata": r.get("metadata")} for r in results[:5]],
                    "summary": summary if isinstance(summary, str) else None,
                    "meta": meta,
                }
            )
        _log_gateway_audit(
            request,
            "semantic_search",
            "semantic_search",
            "success",
            {"count": len(results)},
        )
        return JsonResponse(
            {
                "success": True,
                "results": [{"metadata": r.get("metadata")} for r in results[:10]],
                "meta": {"count": len(results)},
            }
        )
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Semantic search failed",
            extra={"error": str(e)},
        )
        _log_gateway_audit(
            request,
            "semantic_search",
            "semantic_search",
            "error",
            {"error": str(e)[:200]},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Admin copilot ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_admin_copilot(request):
    """POST: { "query": "..." } → admin_copilot with RAG over help/config docs. Returns citations."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:2000]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        context_parts = []
        citations = []
        emb = get_embedding_for_text(query, max_tokens=512)
        if emb:
            for scope in ("help", "config", "default"):
                for r in _search_ai_memory(request, scope, emb, limit=2):
                    context_parts.append(str(r.get("metadata", ""))[:400])
                    citations.append(
                        {
                            "id": r.get("id"),
                            "scope": scope,
                            "metadata": {
                                k: v
                                for k, v in (r.get("metadata") or {}).items()
                                if k not in ("embedding", "raw_text")
                            },
                        }
                    )
        context = "\n".join(context_parts)[:2000] if context_parts else ""
        prompt = (
            get_prompt_template(
                "admin_copilot", {"query": query, "context_block": context}
            )
            or ""
        ).strip() or (
            "You are an admin and configuration assistant. Use the following context to answer.\n\n"
            f"{context}\n\nQuestion: {query}\n\nAnswer concisely; include links or doc refs if relevant."
        )
        result, meta = _gateway_response(
            request, TaskType.ADMIN_COPILOT, prompt, user_query=query
        )
        error_response = _gateway_meta_error_response(
            meta,
            result=result,
            budget_error="AI request budget exceeded for this tenant.",
        )
        if error_response:
            return error_response
        _log_gateway_audit(request, "admin_copilot", "admin_copilot", "success", meta)
        return JsonResponse(
            {"success": True, "response": result, "citations": citations, "meta": meta}
        )
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Admin copilot failed",
            extra={"error": str(e)},
        )
        _log_gateway_audit(
            request, "admin_copilot", "admin_copilot", "error", {"error": str(e)[:200]}
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Toolset 5A: Theme & Experience ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_theme_recommend(request):
    """POST: { "query": "..." } → theme/experience suggestions (structured)."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:1500]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        prompt = (
            get_prompt_template("theme_experience", {"query": query}) or ""
        ).strip() or (
            f"Suggest theme or experience improvements. User request: {query}\n\n"
            'Respond with JSON: {{ "suggestions": [], "rationale": "..." }}. No other text.'
        )
        result, meta = _gateway_response(
            request,
            TaskType.CONFIG_EXPLAIN,
            prompt,
            user_query=query,
            response_schema="theme_experience",
        )
        error_response = _gateway_meta_error_response(meta, result=result)
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "theme_recommend", "config_explain", "success", meta
        )
        out = (
            result
            if isinstance(result, dict)
            else {"suggestions": [], "rationale": str(result)}
        )
        return JsonResponse(
            {
                "success": True,
                "suggestions": out.get("suggestions", []),
                "rationale": out.get("rationale", ""),
                "meta": meta,
            }
        )
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Theme recommend failed",
            extra={"error": str(e)},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Toolset 5B: Feature Control ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_feature_control_explain(request):
    """POST: { "query": "..." } → feature flag explanation."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:1000]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        prompt = (
            get_prompt_template("feature_control", {"query": query}) or ""
        ).strip() or (
            f"Explain feature flags and control. User question: {query}\n\n"
            "Respond concisely with what the feature does and when to enable/disable it."
        )
        result, meta = _gateway_response(
            request, TaskType.CONFIG_EXPLAIN, prompt, user_query=query
        )
        error_response = _gateway_meta_error_response(meta, result=result)
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "feature_control_explain", "config_explain", "success", meta
        )
        return JsonResponse(
            {
                "success": True,
                "explanation": result if isinstance(result, str) else str(result),
                "meta": meta,
            }
        )
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Feature control explain failed",
            extra={"error": str(e)},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Toolset 5C: Report Library ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_report_recommend(request):
    """POST: { "query": "..." } → report recommendations (structured)."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:1000]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        prompt = (
            get_prompt_template("report_library", {"query": query}) or ""
        ).strip() or (
            f"Recommend reports from the library. User need: {query}\n\n"
            'Respond with JSON: {{ "recommendations": [{{ "name", "description", "fit" }}] }}. No other text.'
        )
        result, meta = _gateway_response(
            request,
            TaskType.SETUP_RECOMMEND,
            prompt,
            user_query=query,
            response_schema="report_recommend",
        )
        error_response = _gateway_meta_error_response(meta, result=result)
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "report_recommend", "setup_recommend", "success", meta
        )
        recs = result.get("recommendations", []) if isinstance(result, dict) else []
        return JsonResponse({"success": True, "recommendations": recs, "meta": meta})
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Report recommend failed",
            extra={"error": str(e)},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Toolset 5E: Design Studio ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_design_studio_draft(request):
    """POST: { "query": "..." } → design/layout suggestions (structured)."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:1500]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        prompt = (
            get_prompt_template("design_studio", {"query": query}) or ""
        ).strip() or (
            f"Suggest design or layout changes. User request: {query}\n\n"
            'Respond with JSON: {{ "suggestions": [], "components": [] }}. No other text.'
        )
        result, meta = _gateway_response(
            request,
            TaskType.CONFIG_EXPLAIN,
            prompt,
            user_query=query,
            response_schema="design_studio",
        )
        error_response = _gateway_meta_error_response(meta, result=result)
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "design_studio_draft", "config_explain", "success", meta
        )
        out = (
            result
            if isinstance(result, dict)
            else {"suggestions": [], "components": []}
        )
        return JsonResponse(
            {
                "success": True,
                "suggestions": out.get("suggestions", []),
                "components": out.get("components", []),
                "meta": meta,
            }
        )
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Design studio draft failed",
            extra={"error": str(e)},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Toolset 5F: Live Previews (explain) ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_live_preview_explain(request):
    """POST: { "query": "..." } → explanation of preview behaviour."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:1000]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        prompt = (
            get_prompt_template("live_preview", {"query": query}) or ""
        ).strip() or (
            f"Explain live preview behaviour for setup or design. User question: {query}\n\nAnswer concisely."
        )
        result, meta = _gateway_response(
            request, TaskType.CONFIG_EXPLAIN, prompt, user_query=query
        )
        error_response = _gateway_meta_error_response(meta, result=result)
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "live_preview_explain", "config_explain", "success", meta
        )
        return JsonResponse(
            {
                "success": True,
                "explanation": result if isinstance(result, str) else str(result),
                "meta": meta,
            }
        )
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Live preview explain failed",
            extra={"error": str(e)},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Toolset 5I: Configuration Control Center ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_system_config_explain(request):
    """POST: { "query": "..." } → Configuration Control Center / settings explanation."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:1000]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        prompt = (
            get_prompt_template("system_config", {"query": query}) or ""
        ).strip() or (
            f"Explain Configuration Control Center and related settings options. User question: {query}\n\n"
            "Answer concisely; do not include secrets or internal URLs."
        )
        result, meta = _gateway_response(
            request, TaskType.CONFIG_EXPLAIN, prompt, user_query=query
        )
        error_response = _gateway_meta_error_response(meta, result=result)
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "system_config_explain", "config_explain", "success", meta
        )
        return JsonResponse(
            {
                "success": True,
                "explanation": result if isinstance(result, str) else str(result),
                "meta": meta,
            }
        )
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Configuration Control Center explain failed",
            extra={"error": str(e)},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Wave 2: Dashboard/pack recommendations ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_dashboard_pack_recommend(request):
    """POST: { "query": "..." } → dashboard or pack recommendations."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:1000]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        prompt = (
            get_prompt_template("dashboard_pack_recommend", {"query": query}) or ""
        ).strip() or (
            f"Recommend dashboards or experience packs for: {query}\n\n"
            'Respond with JSON: {{ "dashboards": [], "packs": [], "rationale": "..." }}. No other text.'
        )
        result, meta = _gateway_response(
            request,
            TaskType.SETUP_RECOMMEND,
            prompt,
            user_query=query,
            response_schema="dashboard_pack_recommend",
        )
        error_response = _gateway_meta_error_response(meta, result=result)
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "dashboard_pack_recommend", "setup_recommend", "success", meta
        )
        out = (
            result
            if isinstance(result, dict)
            else {"dashboards": [], "packs": [], "rationale": str(result)}
        )
        return JsonResponse(
            {
                "success": True,
                "dashboards": out.get("dashboards", []),
                "packs": out.get("packs", []),
                "rationale": out.get("rationale", ""),
                "meta": meta,
            }
        )
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Dashboard pack recommend failed",
            extra={"error": str(e)},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


def _parse_support_assistant_body(request):
    from services.ai.support_sanitize import sanitize_support_query

    from apps.portal.ai_surface_context import build_ai_surface_context

    body = json.loads(request.body) if request.body else {}
    query = sanitize_support_query((body.get("query") or "").strip()[:8000])
    surface = build_ai_surface_context(request)
    active_url = (
        (body.get("active_url") or body.get("path") or surface.get("current_path") or "")
        .strip()[:500]
    )
    history = sanitize_support_query(
        (body.get("history") or body.get("interaction_history") or "").strip()[:2000]
    )
    return query, active_url, history


# --- Wave 2: Support assistant (productized) ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_support_assistant(request):
    """POST: { "query": "...", "active_url": "/optional/path" } → first-line support."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    from apps.portal.help_governance import ai_help_enabled_for_request

    if not ai_help_enabled_for_request(request):
        return JsonResponse(
            {"success": False, "error": "ai_help_disabled", "offline_mode": True},
            status=403,
        )
    try:
        query, active_url, history = _parse_support_assistant_body(request)
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        from django.conf import settings as dj_settings

        if getattr(dj_settings, "AI_ENGINE_ROOM_SUPPORT", True):
            from services.ai.gateway import process_platform_query

            school = getattr(request, "school", None)
            engine = process_platform_query(
                request.user,
                active_url,
                query,
                school=school,
                actor_roles=_actor_roles(request),
                actor_is_staff=bool(
                    getattr(request.user, "is_staff", False)
                ),
                actor_is_superuser=bool(
                    getattr(request.user, "is_superuser", False)
                ),
                interaction_history=history,
            )
            meta = engine.get("meta") or {}
            if engine.get("error") and not engine.get("success"):
                return JsonResponse(
                    {"success": False, "error": engine["error"]},
                    status=400,
                )
            _log_gateway_audit(
                request,
                "support_assistant",
                "support_suggest",
                "success" if engine.get("success") else "degraded",
                meta,
            )
            return JsonResponse(
                {
                    "success": bool(engine.get("success")),
                    "response": engine.get("response") or "",
                    "escalation_required": bool(engine.get("escalation_required")),
                    "meta": meta,
                }
            )

        context_parts = []
        emb = get_embedding_for_text(query, max_tokens=512)
        if emb:
            for r in _search_ai_memory(request, "help", emb, limit=3):
                context_parts.append(str(r.get("metadata", ""))[:400])
        context = "\n".join(context_parts)[:1200] if context_parts else ""
        prompt = (
            get_prompt_template(
                "support_suggest", {"query": query, "context_block": context}
            )
            or ""
        ).strip() or (
            f"Based on the following context, suggest a support response.\n\n{context}\n\nUser message: {query}\n\nProvide a helpful, professional reply."
        )
        result, meta = _gateway_response(
            request, TaskType.SUPPORT_SUGGEST, prompt, user_query=query
        )
        error_response = _gateway_meta_error_response(meta, result=result)
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "support_assistant", "support_suggest", "success", meta
        )
        return JsonResponse(
            {
                "success": True,
                "response": result if isinstance(result, str) else str(result),
                "meta": meta,
            }
        )
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Support assistant failed",
            extra={"error": str(e)},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_support_assistant_stream(request):
    """POST JSON → ``text/event-stream`` (delta + done frames)."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    from apps.portal.help_governance import ai_help_enabled_for_request

    if not ai_help_enabled_for_request(request):
        return JsonResponse(
            {"success": False, "error": "ai_help_disabled", "offline_mode": True},
            status=403,
        )
    try:
        query, active_url, history = _parse_support_assistant_body(request)
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        from django.conf import settings as dj_settings

        if not getattr(dj_settings, "AI_ENGINE_ROOM_SUPPORT", True):
            return JsonResponse(
                {"success": False, "error": "AI engine room disabled"}, status=503
            )
        from services.ai.support_stream import iter_support_assistant_sse

        school = getattr(request, "school", None)
        stream = iter_support_assistant_sse(
            request.user,
            active_url,
            query,
            school=school,
            actor_roles=_actor_roles(request),
            actor_is_staff=bool(getattr(request.user, "is_staff", False)),
            actor_is_superuser=bool(getattr(request.user, "is_superuser", False)),
            interaction_history=history,
            request=request,
        )
        response = StreamingHttpResponse(stream, content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Support assistant stream failed",
            extra={"error": str(e)},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Wave 2: Tenant maturity score (backend + optional endpoint) ---
@require_http_methods(["GET", "POST"])
@csrf_protect
@login_required
def api_tenant_maturity(request):
    """GET or POST: returns tenant maturity score and recommendations (computed server-side)."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        _school_id(request)
        # §3.2: Use runtime helper instead of direct tenant site settings read (tenant-facing).
        score = 0
        try:
            from apps.siteconfig.config_service import get_effective_site_settings

            settings_obj = get_effective_site_settings(request=request)
            if settings_obj and getattr(settings_obj, "features", None):
                features = (
                    settings_obj.features
                    if isinstance(settings_obj.features, dict)
                    else {}
                )
                score = min(100, 20 + len(features) * 5)
        except (AttributeError, TypeError, ValueError):
            pass
        recommendations = []
        if score < 50:
            recommendations.append("Enable more setup features to increase maturity.")
        return JsonResponse(
            {
                "success": True,
                "score": score,
                "tier": "starter"
                if score < 40
                else "growth"
                if score < 70
                else "advanced",
                "recommendations": recommendations,
                "meta": {},
            }
        )
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Tenant maturity failed",
            extra={"error": str(e)},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Wave 3: Data quality assistant ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_data_quality_assistant(request):
    """POST: { "query": "..." } → data quality checks, suggestions, or remediation hints (RAG over config/help)."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:2000]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        context_parts = []
        emb = get_embedding_for_text(query, max_tokens=512)
        if emb:
            for scope in ("config", "help", "default"):
                for r in _search_ai_memory(request, scope, emb, limit=2):
                    context_parts.append(str(r.get("metadata", ""))[:400])
        context = "\n".join(context_parts)[:2000] if context_parts else ""
        prompt = (
            get_prompt_template(
                "data_quality", {"query": query, "context_block": context}
            )
            or ""
        ).strip() or (
            "You are a data quality assistant. Based on the context and the user's question, suggest data quality checks, "
            "validation rules, or remediation steps. Be concise and actionable.\n\n"
            f"Context:\n{context}\n\nUser question: {query}\n\nProvide 3–5 concrete suggestions."
        )
        result, meta = _gateway_response(
            request, TaskType.CONFIG_EXPLAIN, prompt, user_query=query
        )
        error_response = _gateway_meta_error_response(meta, result=result)
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "data_quality_assistant", "config_explain", "success", meta
        )
        return JsonResponse(
            {
                "success": True,
                "response": result if isinstance(result, str) else str(result),
                "meta": meta,
            }
        )
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Data quality assistant failed",
            extra={"error": str(e)},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Wave 3: Marketplace ranking / recommendation ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_marketplace_recommend(request):
    """POST: { "query": "...", "institution_type": "..." } → recommended apps/packs with rationale."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or body.get("institution_type") or "").strip()[:1500]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query or institution_type required"},
                status=400,
            )
        prompt = (
            get_prompt_template("marketplace_recommend", {"query": query}) or ""
        ).strip() or (
            f"Recommend marketplace apps or experience packs for: {query}\n\n"
            'Respond with JSON only: { "recommendations": [ { "name", "category", "fit", "rationale" } ], "rationale": "..." }. No other text.'
        )
        result, meta = _gateway_response(
            request,
            TaskType.SETUP_RECOMMEND,
            prompt,
            user_query=query,
            response_schema="marketplace_recommend",
        )
        error_response = _gateway_meta_error_response(meta, result=result)
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "marketplace_recommend", "setup_recommend", "success", meta
        )
        out = (
            result
            if isinstance(result, dict)
            else {"recommendations": [], "rationale": str(result)}
        )
        return JsonResponse(
            {
                "success": True,
                "recommendations": out.get("recommendations", []),
                "rationale": out.get("rationale", ""),
                "meta": meta,
            }
        )
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Marketplace recommend failed",
            extra={"error": str(e)},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


# --- Wave 3: Control-plane intelligence ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_control_plane_intelligence(request):
    """POST: { "query": "..." } → operator-facing insights, runbook hints, or config summary (RAG help/config)."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:2000]
        if not query:
            return JsonResponse(
                {"success": False, "error": "query required"}, status=400
            )
        context_parts = []
        emb = get_embedding_for_text(query, max_tokens=512)
        if emb:
            for scope in ("help", "config", "default"):
                for r in _search_ai_memory(request, scope, emb, limit=3):
                    context_parts.append(str(r.get("metadata", ""))[:400])
        context = "\n".join(context_parts)[:2000] if context_parts else ""
        prompt = (
            get_prompt_template(
                "control_plane_intelligence", {"query": query, "context_block": context}
            )
            or ""
        ).strip() or (
            "You are a control-plane intelligence assistant for platform operators. Use the context to answer concisely. "
            "Provide runbook-style steps or config insights where relevant.\n\n"
            f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
        )
        result, meta = _gateway_response(
            request, TaskType.ADMIN_COPILOT, prompt, user_query=query
        )
        error_response = _gateway_meta_error_response(meta, result=result)
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "control_plane_intelligence", "admin_copilot", "success", meta
        )
        return JsonResponse(
            {
                "success": True,
                "response": result if isinstance(result, str) else str(result),
                "meta": meta,
            }
        )
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Control plane intelligence failed",
            extra={"error": str(e)},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


def _runtime_snapshot_context(request) -> str:
    school = getattr(request, "school", None)
    if not school:
        return (
            "No tenant school on this request. Explain RunMyCampus runtime precedence "
            "(global → region → tenant packs → feature flags) without inventing this tenant's values."
        )
    try:
        from apps.platform_runtime.helpers import get_effective_flags_for_school

        flags = get_effective_flags_for_school(school) or {}
        keys = sorted(str(k) for k in flags.keys())[:60]
        return (
            f"Tenant id (opaque): {getattr(school, 'pk', '')}. "
            f"Sample effective feature-flag keys (names only): {', '.join(keys) or 'none'}."
        )
    except OPTIONAL_GATEWAY_ERRORS:
        return "Runtime snapshot unavailable; explain precedence conceptually only."


def _append_json_snapshot(context_block: str, snapshot: Any, *, label: str) -> str:
    if snapshot is None:
        return context_block
    try:
        blob = json.dumps(snapshot, default=str)[:3500]
    except (TypeError, ValueError):
        blob = str(snapshot)[:3500]
    return f"{context_block}\n{label}: {blob}"


def _guided_assistant_rag_context(
    request, query: str
) -> tuple[str, list[dict[str, Any]]]:
    """Same retrieval pattern as setup assistant: help/config/default AI memory scopes."""
    school_id = _school_id(request)
    citations: list[dict[str, Any]] = []
    if not school_id:
        return "", citations
    context_parts: list[str] = []
    emb = get_embedding_for_text(query, max_tokens=512)
    if not emb:
        return "", citations
    try:
        for scope in ("help", "config", "default"):
            for r in _search_ai_memory(request, scope, emb, limit=2):
                context_parts.append(str(r.get("metadata", ""))[:400])
                citations.append(
                    {
                        "id": r.get("id"),
                        "scope": scope,
                        "metadata": {
                            k: v
                            for k, v in (r.get("metadata") or {}).items()
                            if k not in ("embedding", "raw_text")
                        },
                    }
                )
    except OPTIONAL_GATEWAY_ERRORS:
        return "", citations
    blob = "\n".join(context_parts)[:1200]
    return blob, citations


def _guided_request_grounding(request) -> str:
    """Non-secret request facts so the model can resolve relative paths without inventing hosts."""
    try:
        base = request.build_absolute_uri("/").rstrip("/") + "/"
    except (AttributeError, TypeError, ValueError):
        base = ""
    try:
        host = (request.get_host() or "").strip()
    except (AttributeError, TypeError, ValueError):
        host = ""
    if not base and not host:
        return "Request origin: unknown; describe routes as path-only unless CONTEXT gives a full URL."
    parts = []
    if host:
        parts.append(f"HTTP Host (for same-origin navigation): {host[:200]}")
    if base:
        parts.append(
            f"Absolute base URL for this request (prefix for relative paths in CONTEXT): {base[:240]}"
        )
    return "\n".join(parts)


def _api_guided_domain_assistant(
    request,
    *,
    task_type: Any,
    audit_feature: str,
    prompt_key: str,
    context_block: str,
) -> JsonResponse:
    from services.ai_permissions import get_ai_permission_for_user

    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    query = (body.get("query") or "").strip()[:2000]
    if not query:
        return JsonResponse({"success": False, "error": "query required"}, status=400)
    task_key = (
        task_type.value if hasattr(task_type, "value") else str(task_type or "")
    )
    school = getattr(request, "school", None)
    if not get_ai_permission_for_user(request.user, task_key, school):
        return _gateway_permission_denied_response(
            {"outcome": "permission_denied", "error": "AI permission denied for this task"}
        )
    ctx = f"{_guided_request_grounding(request)}\n\n{context_block}"
    if audit_feature == "studio_os_assistant":
        mode = str(body.get("studio_mode") or "").strip()[:64]
        ctx = f"{ctx}\nUser studio_mode hint: {mode or 'unknown'}."
    ctx = _append_json_snapshot(
        ctx,
        body.get("context_snapshot"),
        label="Optional user-supplied snapshot (must not contain secrets)",
    )
    rag_blob, rag_citations = _guided_assistant_rag_context(request, query)
    if rag_blob:
        ctx = (
            f"{ctx}\nRetrieved platform memory snippets (use when relevant; do not contradict CONTEXT above):\n"
            f"{rag_blob}"
        )
    prompt = (
        get_prompt_template(
            prompt_key,
            {"query": query, "context_block": ctx},
        )
        or ""
    ).strip() or (
        "GROUNDING: Use CONTEXT only for product-specific facts; if insufficient, say so in summary and add cautions. "
        "Never output secrets or fabricated URLs.\n\n"
        "You are a precise product assistant.\n\n"
        "Respond with JSON only:\n"
        '{"summary": "string", "actions": [{"title": "string", "detail": "string"}], '
        '"cautions": ["string"], "references": ["string"]}\n\n'
        f"CONTEXT:\n{ctx}\n\nQUESTION:\n{query}\n"
    )
    try:
        result, meta = _gateway_response(
            request,
            task_type,
            prompt,
            user_query=query,
            response_schema="guided_assistant",
            rag_snippets=rag_citations,
        )
        error_response = _gateway_meta_error_response(
            meta,
            result=result,
            budget_error="AI request budget exceeded for this tenant.",
        )
        if error_response:
            return error_response
        _log_gateway_audit(request, audit_feature, str(task_type), "success", meta)
        out = result if isinstance(result, dict) else {}
        if not str(out.get("summary") or "").strip():
            from apps.portal.ai_provider import ollama_require_live

            if ollama_require_live() or meta.get("live_ai_unavailable"):
                from services.ai_unavailable import build_ollama_unavailable_guided

                out = build_ollama_unavailable_guided(user_query=query)
                meta = {
                    **(meta or {}),
                    "live_ai_unavailable": True,
                    "empty_summary_repaired": True,
                }
            else:
                from services.ai_guided_fallback import build_guided_fallback

                task_key = (
                    task_type.value if hasattr(task_type, "value") else str(task_type or "")
                )
                out = build_guided_fallback(
                    task_type=task_key,
                    user_query=query,
                    rag_snippets=rag_citations,
                    live_provider_available=bool(
                        meta.get("provider") == "ollama" or meta.get("tier") == "ollama"
                    ),
                    metadata={
                        **(meta or {}),
                        "request": request,
                        "school": getattr(request, "school", None),
                        "rag_snippets": rag_citations,
                    },
                )
                meta = {**(meta or {}), "degraded": True, "empty_summary_repaired": True}
        payload = {
            "success": True,
            "guided": {
                "summary": out.get("summary", ""),
                "actions": out.get("actions", []),
                "cautions": out.get("cautions", []),
                "references": out.get("references", []),
            },
            "meta": meta,
        }
        if rag_citations:
            payload["citations"] = rag_citations
        return JsonResponse(payload)
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            f"portal.views_ai_gateway: {audit_feature} failed",
            extra={"error": str(e)},
        )
        _log_gateway_audit(
            request, audit_feature, str(task_type), "error", {"error": str(e)[:200]}
        )
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


# --- Domain-guided assistants (Studio, interop, runtime, observability, billing, trust) ---


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_interop_assistant(request):
    """POST: { query, context_snapshot? } → structured guidance for district/LMS interop (no secret echo)."""
    ctx = (
        "Grounding: Tenant District & LMS interop hub lives at /authentication/backend/district-lms-interop/. "
        "OneRoster consumer API: /api/oneroster/v1p1/ with school_slug. Readiness: /api/interop/oneroster/, "
        "/api/interop/lti13/. Clever/ClassLink native HTTP uses district-provisioned bearer tokens only via hub forms; "
        "never ask users to paste tokens into chat."
    )
    return _api_guided_domain_assistant(
        request,
        task_type=TaskType.INTEROP_ASSISTANT,
        audit_feature="interop_assistant",
        prompt_key="interop_assistant",
        context_block=ctx,
    )


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_runtime_config_explain(request):
    """POST: { query, context_snapshot? } → structured guidance using effective-flag key sample when tenant bound."""
    ctx = _runtime_snapshot_context(request)
    return _api_guided_domain_assistant(
        request,
        task_type=TaskType.RUNTIME_CONFIG_EXPLAIN,
        audit_feature="runtime_config_explain",
        prompt_key="runtime_config_explain",
        context_block=ctx,
    )


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_observability_assistant(request):
    """POST: { query, context_snapshot? } → SLO/runbook-style guidance for operators (staff/superuser)."""
    ctx = (
        "Audience: platform operators. Prefer citing internal routes: /api/observability/slo-dashboard/, "
        "/api/health/, /metrics/, PlatformEventLog patterns. Do not fabricate incident IDs."
    )
    return _api_guided_domain_assistant(
        request,
        task_type=TaskType.OBSERVABILITY_ASSISTANT,
        audit_feature="observability_assistant",
        prompt_key="observability_assistant",
        context_block=ctx,
    )


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_billing_usage_explain(request):
    """POST: { query, context_snapshot? } → billing/SKU/usage explanations; finance or staff only."""
    ctx = (
        "Explain entitlements, usage meters, and plan concepts. Do not output card numbers or full invoice lines. "
        "If context_snapshot includes aggregates only, reference them cautiously."
    )
    return _api_guided_domain_assistant(
        request,
        task_type=TaskType.BILLING_USAGE_EXPLAIN,
        audit_feature="billing_usage_explain",
        prompt_key="billing_usage_explain",
        context_block=ctx,
    )


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_trust_compliance_assistant(request):
    """POST: { query, context_snapshot? } → trust center / compliance checklist style guidance (staff)."""
    ctx = (
        "Ground with published trust and compliance docs only; remind that AI text is not legal advice. "
        "Reference FERPA/GDPR themes at high level; point operators to trust center pages for canonical wording."
    )
    return _api_guided_domain_assistant(
        request,
        task_type=TaskType.TRUST_COMPLIANCE_ASSISTANT,
        audit_feature="trust_compliance_assistant",
        prompt_key="trust_compliance_assistant",
        context_block=ctx,
    )


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_studio_os_assistant(request):
    """POST: { query, context_snapshot?, studio_mode? } → next steps across Studio OS modes (preview/apply still manual)."""
    ctx = (
        "Studio OS modes: experience, automation, output, launch, control. "
        "Recommend verify → preview → publish/rollback; packages/engine apply is authoritative."
    )
    return _api_guided_domain_assistant(
        request,
        task_type=TaskType.STUDIO_OS_ASSISTANT,
        audit_feature="studio_os_assistant",
        prompt_key="studio_os_assistant",
        context_block=ctx,
    )


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_ai_feedback(request):
    """POST: record operator review for an AI result so review-loop metrics are queryable."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        task_type = str(body.get("task_type") or "").strip()
        tier = str(body.get("tier") or "").strip().lower()
        if not task_type or not tier:
            return JsonResponse(
                {"success": False, "error": "task_type and tier required"}, status=400
            )
        accepted = _parse_optional_bool(body.get("accepted"))
        manual_correction = _parse_optional_bool(body.get("manual_correction"))
        if accepted is None and manual_correction is None:
            return JsonResponse(
                {"success": False, "error": "accepted or manual_correction required"},
                status=400,
            )
        feature = str(body.get("feature") or task_type).strip()[:120]
        request_id = str(body.get("request_id") or "").strip()[:64] or None
        request_date = str(body.get("request_date") or "").strip()[:32] or None
        school_id = _school_id(request)
        feedback_meta = record_feedback(
            task_type,
            tier,
            tenant_id=school_id,
            school_id=school_id,
            accepted=accepted,
            manual_correction=manual_correction,
            request_date=request_date,
            request_id=request_id,
        )
        action = AuditLog.Action.UPDATE
        if accepted is True:
            action = AuditLog.Action.APPROVE
        elif accepted is False:
            action = AuditLog.Action.REJECT
        AuditLog.objects.create(
            user=getattr(request, "user", None),
            ip_address=(request.META.get("REMOTE_ADDR") or "")[:45],
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:500],
            action=action,
            model_name="AIGatewayFeedback",
            object_id=request_id or feature,
            object_repr=f"AI feedback {feature}",
            app_label="portal",
            reason=task_type,
            sensitivity=AuditLog.Sensitivity.LOW,
            new_values={"feature": feature, **feedback_meta},
        )
        if accepted is False or manual_correction is True:
            try:
                from apps.feedback.models import SupportAIInteractionReview
                from apps.portal.kb_context import is_operator_help_request
                from django.utils import translation

                query_raw = str(body.get("query") or "")[:500]
                SupportAIInteractionReview.objects.create(
                    school=getattr(request, "school", None),
                    user=request.user,
                    query_fingerprint=SupportAIInteractionReview.fingerprint(
                        query_raw
                    ),
                    active_url=str(body.get("active_url") or "")[:500],
                    outcome=str(body.get("outcome") or task_type)[:64],
                    thumbs="down" if accepted is False else "corrected",
                    language=(translation.get_language() or "")[:12],
                    is_operator=is_operator_help_request(request),
                )
            except Exception:
                pass
        return JsonResponse({"success": True, "meta": feedback_meta})
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except ValueError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: AI feedback failed",
            extra={"error": str(e)},
        )
        _log_gateway_audit(
            request, "ai_feedback", "feedback", "error", {"error": str(e)[:200]}
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )


@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_support_session_rating(request):
    """POST: CSAT thumbs/stars after support SSE (batch 1353, fingerprint-only)."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        thumbs = str(body.get("thumbs") or "").strip().lower()[:8]
        stars_raw = body.get("stars")
        stars = None
        if stars_raw is not None:
            stars = int(stars_raw)
            if stars < 1 or stars > 5:
                return JsonResponse(
                    {"success": False, "error": "stars must be 1-5"}, status=400
                )
        if thumbs not in ("up", "down") and stars is None:
            return JsonResponse(
                {"success": False, "error": "thumbs or stars required"}, status=400
            )
        query_raw = str(body.get("query") or "")[:500]
        from apps.feedback.models import SupportAISessionRating, SupportDeflectionEvent
        from apps.portal.kb_context import is_operator_help_request

        SupportAISessionRating.objects.create(
            school=getattr(request, "school", None),
            user=request.user,
            query_fingerprint=SupportDeflectionEvent.fingerprint(query_raw),
            task_type=str(body.get("task_type") or "support_assistant")[:64],
            thumbs=thumbs,
            stars=stars,
            active_url=str(body.get("active_url") or "")[:500],
            is_operator=is_operator_help_request(request),
        )
        if thumbs == "down":
            try:
                from apps.feedback.models import SupportAIInteractionReview

                SupportAIInteractionReview.objects.create(
                    school=getattr(request, "school", None),
                    user=request.user,
                    query_fingerprint=SupportAIInteractionReview.fingerprint(
                        query_raw
                    ),
                    active_url=str(body.get("active_url") or "")[:500],
                    outcome=str(body.get("task_type") or "support_assistant")[:64],
                    thumbs="down",
                    language=(body.get("language") or "")[:12],
                    is_operator=is_operator_help_request(request),
                )
            except Exception:
                pass
        return JsonResponse({"success": True})
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)


# --- Migration suggest ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_migration_suggest(request):
    """POST: { "source_fields": [...], "target_fields": [...] or "source_sample": {}, "target_schema": {} } → migration_mapping."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        source_fields = body.get("source_fields") or body.get("source_sample")
        target_fields = body.get("target_fields") or body.get("target_schema")
        if not source_fields and not target_fields:
            return JsonResponse(
                {
                    "success": False,
                    "error": "source_fields and target_fields (or source_sample/target_schema) required",
                },
                status=400,
            )
        prompt = (
            get_prompt_template(
                "migration_mapping",
                {
                    "query": "Suggest field mappings",
                    "source_fields": str(source_fields)[:1500],
                    "target_fields": str(target_fields)[:1500],
                },
            )
            or ""
        ).strip() or (
            'Suggest field mappings as JSON array. Each item: { "source_field", "target_field", "confidence" (0-1), "notes" }.\n\n'
            f"Source: {str(source_fields)[:1500]}\nTarget: {str(target_fields)[:1500]}\n\nRespond with JSON array only. No other text."
        )
        result, meta = _gateway_response(
            request,
            TaskType.MIGRATION_MAPPING,
            prompt,
            response_schema="migration_mapping",
        )
        error_response = _gateway_meta_error_response(
            meta,
            result=result,
            budget_error="AI request budget exceeded for this tenant.",
        )
        if error_response:
            return error_response
        _log_gateway_audit(
            request, "migration_suggest", "migration_mapping", "success", meta
        )
        return JsonResponse(
            {
                "success": True,
                "mappings": result if isinstance(result, list) else [],
                "meta": meta,
            }
        )
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except GATEWAY_VIEW_ERRORS as e:
        log_view_exception(
            request,
            "portal.views_ai_gateway: Migration suggest failed",
            extra={"error": str(e)},
        )
        _log_gateway_audit(
            request,
            "migration_suggest",
            "migration_mapping",
            "error",
            {"error": str(e)[:200]},
        )
        return JsonResponse(
            {"success": False, "error": "Service unavailable"}, status=503
        )
