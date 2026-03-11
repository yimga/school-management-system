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
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from apps.compliance.models import AuditLog
from apps.portal.views_ai_copilot import _check_rate_limit
from apps.siteconfig.prompt_registry import get_prompt_template
from services.ai_gateway import TaskType, invoke
from services.ai_memory import AIMemoryService, get_embedding_for_text
from services.inference import strip_pii_for_inference

logger = logging.getLogger(__name__)
OPTIONAL_GATEWAY_ERRORS = (AttributeError, DatabaseError, ImportError, TypeError, ValueError)

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
    return str(school.id) if school and getattr(school, "id", None) else None


def _redact_audit_meta(meta: dict | None) -> dict:
    """Ensure no prompt/response or other sensitive content is stored in audit new_values."""
    if not meta:
        return {}
    safe = {}
    skip_keys = {"prompt", "response", "user_query", "query", "text", "content"}
    for k, v in meta.items():
        if k.lower() in skip_keys and isinstance(v, str) and len(v) > 100:
            safe[k] = "[redacted]"
        elif isinstance(v, dict):
            safe[k] = _redact_audit_meta(v)
        else:
            safe[k] = v
    return safe


def _log_gateway_audit(request, feature: str, task_type: str, outcome: str, meta: dict | None = None):
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
    except Exception as e:
        logger.debug("Gateway audit log failed: %s", e)


def _gateway_response(request, task_type: str, prompt: str, user_query: str = "", response_schema: str | None = None):
    md = {
        "request": request,
        "school_id": _school_id(request),
        "tenant_id": _school_id(request),
    }
    result, meta = invoke(task_type, prompt, user_query=user_query, metadata=md, response_schema=response_schema)
    return result, meta


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
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        school_id = _school_id(request)
        context_parts = []
        citations = []
        emb = get_embedding_for_text(query, max_tokens=512)
        if emb:
            for r in AIMemoryService.search_similar(school_id, "default", emb, limit=5):
                context_parts.append(str(r.get("metadata", ""))[:400])
                citations.append({
                    "id": r.get("id"),
                    "scope": "default",
                    "metadata": {k: v for k, v in (r.get("metadata") or {}).items() if k not in ("embedding", "raw_text")},
                })
        context = "\n".join(context_parts)[:1200] if context_parts else ""
        try:
            prompt = get_prompt_template("setup_assistant", {"query": query, "context_block": context})
        except OPTIONAL_GATEWAY_ERRORS:
            prompt = f"You are a Setup Studio assistant. Answer concisely and helpfully.\n\n"
            if context:
                prompt += f"Relevant context:\n{context}\n\n"
            prompt += f"User question: {query}\n\nProvide 3–5 short actionable setup tips or explain the requested config."
        result, meta = _gateway_response(request, TaskType.SETUP_RECOMMEND, prompt, user_query=query)
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded for this tenant.", "meta": meta}, status=429)
        _log_gateway_audit(request, "setup_assistant", "setup_recommend", "success", meta)
        return JsonResponse({"success": True, "response": result, "citations": citations, "meta": meta})
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.exception("Setup assistant failed")
        _log_gateway_audit(request, "setup_assistant", "setup_recommend", "error", {"error": str(e)[:200]})
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
        description = (body.get("description") or body.get("query") or "").strip()[:1500]
        if not description:
            return JsonResponse({"success": False, "error": "description required"}, status=400)
        prompt = (
            f"Generate a workflow definition as JSON only. User request: {description}\n\n"
            "Respond with a single JSON object with keys: name (string), trigger_type (string), "
            "steps (array of { action, role, config }), description (string). No other text."
        )
        result, meta = _gateway_response(
            request, TaskType.WORKFLOW_DRAFT, prompt, user_query=description, response_schema="workflow_draft"
        )
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded for this tenant.", "meta": meta}, status=429)
        _log_gateway_audit(request, "workflow_draft", "workflow_draft", "success", meta)
        return JsonResponse({"success": True, "draft": result if isinstance(result, dict) else {"description": result}, "meta": meta})
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.exception("Workflow draft failed")
        _log_gateway_audit(request, "workflow_draft", "workflow_draft", "error", {"error": str(e)[:200]})
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "query or policy_text required"}, status=400)
        school_id = _school_id(request)
        context_parts = []
        citations = []
        emb = get_embedding_for_text(query, max_tokens=512)
        if emb:
            for r in AIMemoryService.search_similar(school_id, "policy", emb, limit=5):
                context_parts.append(str(r.get("metadata", ""))[:400])
                citations.append({
                    "id": r.get("id"),
                    "scope": "policy",
                    "metadata": {k: v for k, v in (r.get("metadata") or {}).items() if k not in ("embedding", "raw_text")},
                })
        if not context_parts and emb:
            for r in AIMemoryService.search_similar(school_id, "default", emb, limit=3):
                context_parts.append(str(r.get("metadata", ""))[:400])
                citations.append({"id": r.get("id"), "scope": "default", "metadata": {k: v for k, v in (r.get("metadata") or {}).items() if k not in ("embedding", "raw_text")}})
        context = "\n".join(context_parts)[:1200] if context_parts else ""
        try:
            prompt = get_prompt_template("policy_explain", {"query": query, "context_block": context})
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
            request, TaskType.POLICY_EXPLAIN, prompt, user_query=query, response_schema="policy_explain"
        )
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded for this tenant.", "meta": meta}, status=429)
        _log_gateway_audit(request, "policy_explain", "policy_explain", "success", meta)
        return JsonResponse({"success": True, "explanation": result if isinstance(result, dict) else {"summary": result}, "citations": citations, "meta": meta})
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.exception("Policy explain failed")
        _log_gateway_audit(request, "policy_explain", "policy_explain", "error", {"error": str(e)[:200]})
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "text required"}, status=400)
        safe_text = strip_pii_for_inference(text)
        prompt = (
            f"Classify this document. Respond with JSON only: {{ \"category\": \"...\", \"tags\": [\"...\"], \"confidence\": 0.0-1.0 }}.\n\nDocument excerpt: {safe_text[:2000]}\n\nNo other text."
        )
        result, meta = _gateway_response(
            request, TaskType.DOC_CLASSIFY, prompt, user_query=text[:500], response_schema="doc_classify"
        )
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded for this tenant.", "meta": meta}, status=429)
        _log_gateway_audit(request, "document_classify", "doc_classify", "success", meta)
        return JsonResponse({"success": True, "classification": result if isinstance(result, dict) else {"category": "general"}, "meta": meta})
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.exception("Document classify failed")
        _log_gateway_audit(request, "document_classify", "doc_classify", "error", {"error": str(e)[:200]})
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        school_id = _school_id(request)
        embedding = get_embedding_for_text(query, max_tokens=512)
        if not embedding:
            return JsonResponse({"success": True, "results": [], "meta": {"reason": "embedding_unavailable"}})
        results = AIMemoryService.search_similar(school_id, scope, embedding, limit=10)
        # Optional: summarize top result via gateway
        if results and query:
            prompt = f"Based on this context, answer briefly: {query}\n\nContext: {str(results[0].get('metadata', ''))[:1500]}"
            summary, meta = _gateway_response(request, TaskType.SEMANTIC_SEARCH, prompt, user_query=query)
            if meta.get("budget_exceeded"):
                return JsonResponse({"success": False, "error": "AI request budget exceeded for this tenant.", "meta": meta}, status=429)
            _log_gateway_audit(request, "semantic_search", "semantic_search", "success", meta)
            return JsonResponse({
                "success": True,
                "results": [{"metadata": r.get("metadata")} for r in results[:5]],
                "summary": summary if isinstance(summary, str) else None,
                "meta": meta,
            })
        _log_gateway_audit(request, "semantic_search", "semantic_search", "success", {"count": len(results)})
        return JsonResponse({
            "success": True,
            "results": [{"metadata": r.get("metadata")} for r in results[:10]],
            "meta": {"count": len(results)},
        })
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.exception("Semantic search failed")
        _log_gateway_audit(request, "semantic_search", "semantic_search", "error", {"error": str(e)[:200]})
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        school_id = _school_id(request)
        context_parts = []
        citations = []
        emb = get_embedding_for_text(query, max_tokens=512)
        if emb:
            for scope in ("help", "config", "default"):
                for r in AIMemoryService.search_similar(school_id, scope, emb, limit=2):
                    context_parts.append(str(r.get("metadata", ""))[:400])
                    citations.append({
                        "id": r.get("id"),
                        "scope": scope,
                        "metadata": {k: v for k, v in (r.get("metadata") or {}).items() if k not in ("embedding", "raw_text")},
                    })
        context = "\n".join(context_parts)[:2000] if context_parts else ""
        prompt = (get_prompt_template("admin_copilot", {"query": query, "context_block": context}) or "").strip() or (
            "You are an admin and configuration assistant. Use the following context to answer.\n\n"
            f"{context}\n\nQuestion: {query}\n\nAnswer concisely; include links or doc refs if relevant."
        )
        result, meta = _gateway_response(request, TaskType.ADMIN_COPILOT, prompt, user_query=query)
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded for this tenant.", "meta": meta}, status=429)
        _log_gateway_audit(request, "admin_copilot", "admin_copilot", "success", meta)
        return JsonResponse({"success": True, "response": result, "citations": citations, "meta": meta})
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.exception("Admin copilot failed")
        _log_gateway_audit(request, "admin_copilot", "admin_copilot", "error", {"error": str(e)[:200]})
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        prompt = (get_prompt_template("theme_experience", {"query": query}) or "").strip() or (
            f"Suggest theme or experience improvements. User request: {query}\n\n"
            "Respond with JSON: {{ \"suggestions\": [], \"rationale\": \"...\" }}. No other text."
        )
        result, meta = _gateway_response(request, TaskType.CONFIG_EXPLAIN, prompt, user_query=query)
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded.", "meta": meta}, status=429)
        _log_gateway_audit(request, "theme_recommend", "config_explain", "success", meta)
        out = result if isinstance(result, dict) else {"suggestions": [], "rationale": str(result)}
        return JsonResponse({"success": True, "suggestions": out.get("suggestions", []), "rationale": out.get("rationale", ""), "meta": meta})
    except Exception as e:
        logger.exception("Theme recommend failed")
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        prompt = (get_prompt_template("feature_control", {"query": query}) or "").strip() or (
            f"Explain feature flags and control. User question: {query}\n\n"
            "Respond concisely with what the feature does and when to enable/disable it."
        )
        result, meta = _gateway_response(request, TaskType.CONFIG_EXPLAIN, prompt, user_query=query)
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded.", "meta": meta}, status=429)
        _log_gateway_audit(request, "feature_control_explain", "config_explain", "success", meta)
        return JsonResponse({"success": True, "explanation": result if isinstance(result, str) else str(result), "meta": meta})
    except Exception as e:
        logger.exception("Feature control explain failed")
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        prompt = (get_prompt_template("report_library", {"query": query}) or "").strip() or (
            f"Recommend reports from the library. User need: {query}\n\n"
            "Respond with JSON: {{ \"recommendations\": [{{ \"name\", \"description\", \"fit\" }}] }}. No other text."
        )
        result, meta = _gateway_response(request, TaskType.SETUP_RECOMMEND, prompt, user_query=query)
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded.", "meta": meta}, status=429)
        _log_gateway_audit(request, "report_recommend", "setup_recommend", "success", meta)
        recs = result.get("recommendations", []) if isinstance(result, dict) else []
        return JsonResponse({"success": True, "recommendations": recs, "meta": meta})
    except Exception as e:
        logger.exception("Report recommend failed")
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        prompt = (get_prompt_template("design_studio", {"query": query}) or "").strip() or (
            f"Suggest design or layout changes. User request: {query}\n\n"
            "Respond with JSON: {{ \"suggestions\": [], \"components\": [] }}. No other text."
        )
        result, meta = _gateway_response(request, TaskType.CONFIG_EXPLAIN, prompt, user_query=query)
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded.", "meta": meta}, status=429)
        _log_gateway_audit(request, "design_studio_draft", "config_explain", "success", meta)
        out = result if isinstance(result, dict) else {"suggestions": [], "components": []}
        return JsonResponse({"success": True, "suggestions": out.get("suggestions", []), "components": out.get("components", []), "meta": meta})
    except Exception as e:
        logger.exception("Design studio draft failed")
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        prompt = f"Explain live preview behaviour for setup or design. User question: {query}\n\nAnswer concisely."
        result, meta = _gateway_response(request, TaskType.CONFIG_EXPLAIN, prompt, user_query=query)
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded.", "meta": meta}, status=429)
        _log_gateway_audit(request, "live_preview_explain", "config_explain", "success", meta)
        return JsonResponse({"success": True, "explanation": result if isinstance(result, str) else str(result), "meta": meta})
    except Exception as e:
        logger.exception("Live preview explain failed")
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


# --- Toolset 5I: System Configuration ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_system_config_explain(request):
    """POST: { "query": "..." } → system config explanation."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:1000]
        if not query:
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        prompt = (get_prompt_template("system_config", {"query": query}) or "").strip() or (
            f"Explain system configuration options. User question: {query}\n\n"
            "Answer concisely; do not include secrets or internal URLs."
        )
        result, meta = _gateway_response(request, TaskType.CONFIG_EXPLAIN, prompt, user_query=query)
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded.", "meta": meta}, status=429)
        _log_gateway_audit(request, "system_config_explain", "config_explain", "success", meta)
        return JsonResponse({"success": True, "explanation": result if isinstance(result, str) else str(result), "meta": meta})
    except Exception as e:
        logger.exception("System config explain failed")
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        prompt = f"Recommend dashboards or experience packs for: {query}\n\nRespond with JSON: {{ \"dashboards\": [], \"packs\": [], \"rationale\": \"...\" }}. No other text."
        result, meta = _gateway_response(request, TaskType.SETUP_RECOMMEND, prompt, user_query=query)
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded.", "meta": meta}, status=429)
        _log_gateway_audit(request, "dashboard_pack_recommend", "setup_recommend", "success", meta)
        out = result if isinstance(result, dict) else {"dashboards": [], "packs": [], "rationale": str(result)}
        return JsonResponse({"success": True, "dashboards": out.get("dashboards", []), "packs": out.get("packs", []), "rationale": out.get("rationale", ""), "meta": meta})
    except Exception as e:
        logger.exception("Dashboard pack recommend failed")
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


# --- Wave 2: Support assistant (productized) ---
@require_http_methods(["POST"])
@csrf_protect
@login_required
def api_support_assistant(request):
    """POST: { "query": "..." } → support response suggestion with RAG."""
    rate_err = _gateway_rate_limit(request)
    if rate_err:
        return rate_err
    try:
        body = json.loads(request.body) if request.body else {}
        query = (body.get("query") or "").strip()[:2000]
        if not query:
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        school_id = _school_id(request)
        context_parts = []
        emb = get_embedding_for_text(query, max_tokens=512)
        if emb:
            for r in AIMemoryService.search_similar(school_id, "help", emb, limit=3):
                context_parts.append(str(r.get("metadata", ""))[:400])
        context = "\n".join(context_parts)[:1200] if context_parts else ""
        prompt = (get_prompt_template("support_suggest", {"query": query, "context_block": context}) or "").strip() or (
            f"Based on the following context, suggest a support response.\n\n{context}\n\nUser message: {query}\n\nProvide a helpful, professional reply."
        )
        result, meta = _gateway_response(request, TaskType.SUPPORT_SUGGEST, prompt, user_query=query)
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded.", "meta": meta}, status=429)
        _log_gateway_audit(request, "support_assistant", "support_suggest", "success", meta)
        return JsonResponse({"success": True, "response": result if isinstance(result, str) else str(result), "meta": meta})
    except Exception as e:
        logger.exception("Support assistant failed")
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
        school_id = _school_id(request)
        # Deterministic score from config/features (no LLM required for base score)
        from apps.siteconfig.models import SiteSettings
        score = 0
        try:
            settings_obj = SiteSettings.objects.filter(school_id=school_id).first()
            if settings_obj and getattr(settings_obj, "features", None):
                features = settings_obj.features if isinstance(settings_obj.features, dict) else {}
                score = min(100, 20 + len(features) * 5)
        except Exception:
            pass
        recommendations = []
        if score < 50:
            recommendations.append("Enable more setup features to increase maturity.")
        return JsonResponse({
            "success": True,
            "score": score,
            "tier": "starter" if score < 40 else "growth" if score < 70 else "advanced",
            "recommendations": recommendations,
            "meta": {},
        })
    except Exception as e:
        logger.exception("Tenant maturity failed")
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        school_id = _school_id(request)
        context_parts = []
        emb = get_embedding_for_text(query, max_tokens=512)
        if emb:
            for scope in ("config", "help", "default"):
                for r in AIMemoryService.search_similar(school_id, scope, emb, limit=2):
                    context_parts.append(str(r.get("metadata", ""))[:400])
        context = "\n".join(context_parts)[:2000] if context_parts else ""
        prompt = (
            "You are a data quality assistant. Based on the context and the user's question, suggest data quality checks, "
            "validation rules, or remediation steps. Be concise and actionable.\n\n"
            f"Context:\n{context}\n\nUser question: {query}\n\nProvide 3–5 concrete suggestions."
        )
        result, meta = _gateway_response(request, TaskType.CONFIG_EXPLAIN, prompt, user_query=query)
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded.", "meta": meta}, status=429)
        _log_gateway_audit(request, "data_quality_assistant", "config_explain", "success", meta)
        return JsonResponse({"success": True, "response": result if isinstance(result, str) else str(result), "meta": meta})
    except Exception as e:
        logger.exception("Data quality assistant failed")
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "query or institution_type required"}, status=400)
        prompt = (
            f"Recommend marketplace apps or experience packs for: {query}\n\n"
            "Respond with JSON only: { \"recommendations\": [ { \"name\", \"category\", \"fit\", \"rationale\" } ], \"rationale\": \"...\" }. No other text."
        )
        result, meta = _gateway_response(request, TaskType.SETUP_RECOMMEND, prompt, user_query=query)
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded.", "meta": meta}, status=429)
        _log_gateway_audit(request, "marketplace_recommend", "setup_recommend", "success", meta)
        out = result if isinstance(result, dict) else {"recommendations": [], "rationale": str(result)}
        return JsonResponse({"success": True, "recommendations": out.get("recommendations", []), "rationale": out.get("rationale", ""), "meta": meta})
    except Exception as e:
        logger.exception("Marketplace recommend failed")
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "query required"}, status=400)
        school_id = _school_id(request)
        context_parts = []
        emb = get_embedding_for_text(query, max_tokens=512)
        if emb:
            for scope in ("help", "config", "default"):
                for r in AIMemoryService.search_similar(school_id, scope, emb, limit=3):
                    context_parts.append(str(r.get("metadata", ""))[:400])
        context = "\n".join(context_parts)[:2000] if context_parts else ""
        prompt = (
            "You are a control-plane intelligence assistant for platform operators. Use the context to answer concisely. "
            "Provide runbook-style steps or config insights where relevant.\n\n"
            f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"
        )
        result, meta = _gateway_response(request, TaskType.ADMIN_COPILOT, prompt, user_query=query)
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded.", "meta": meta}, status=429)
        _log_gateway_audit(request, "control_plane_intelligence", "admin_copilot", "success", meta)
        return JsonResponse({"success": True, "response": result if isinstance(result, str) else str(result), "meta": meta})
    except Exception as e:
        logger.exception("Control plane intelligence failed")
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)


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
            return JsonResponse({"success": False, "error": "source_fields and target_fields (or source_sample/target_schema) required"}, status=400)
        prompt = (
            "Suggest field mappings as JSON array. Each item: { \"source_field\", \"target_field\", \"confidence\" (0-1), \"notes\" }.\n\n"
            f"Source: {str(source_fields)[:1500]}\nTarget: {str(target_fields)[:1500]}\n\nRespond with JSON array only. No other text."
        )
        result, meta = _gateway_response(
            request, TaskType.MIGRATION_MAPPING, prompt, response_schema="migration_mapping"
        )
        if meta.get("budget_exceeded"):
            return JsonResponse({"success": False, "error": "AI request budget exceeded for this tenant.", "meta": meta}, status=429)
        _log_gateway_audit(request, "migration_suggest", "migration_mapping", "success", meta)
        return JsonResponse({
            "success": True,
            "mappings": result if isinstance(result, list) else [],
            "meta": meta,
        })
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.exception("Migration suggest failed")
        _log_gateway_audit(request, "migration_suggest", "migration_mapping", "error", {"error": str(e)[:200]})
        return JsonResponse({"success": False, "error": "Service unavailable"}, status=503)
