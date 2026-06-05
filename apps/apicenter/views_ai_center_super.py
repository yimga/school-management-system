"""Super-operator AI Center surfaces (/super/ai-center/*)."""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods

from apps.schools.control_plane import require_super_access_with_host
from services.ai_center.friction_analysis import analyze_friction_signals, friction_topics_for_operator
from services.ai_center.indexing import build_platform_index, search_platform_knowledge
from services.ai_center.kb_generator import (
    generate_faqs_for_module,
    generate_kb_article_from_code_change,
    generate_kb_article_from_route,
    generate_operator_runbook,
    generate_release_note_from_feature,
    generate_tenant_guide,
    propose_faqs_from_feedback,
    propose_help_topics_from_errors,
)
from services.ai_center.query_service import answer_platform_question


def _cp_context(request: HttpRequest, *, title: str, active: str) -> dict:
    return {
        "page_title": title,
        "ai_center_active": active,
        "ai_center_home_url": reverse("super:ai_center_home"),
        "ai_inventory_url": reverse("super:ai_center_inventory"),
        "ai_kb_drafts_url": reverse("super:ai_center_kb_drafts"),
        "ai_friction_url": reverse("super:ai_center_friction"),
        "ai_settings_url": reverse("super:ai_center_settings"),
        "ai_query_url": reverse("super:ai_center_query"),
        "ai_generate_kb_url": reverse("super:ai_center_generate_kb"),
        "ai_faq_candidates_url": reverse("super:ai_center_faq_candidates"),
        "ai_kb_tools_url": reverse("super:ai_center_kb_tools"),
        "ai_agentic_url": reverse("super:ai_center_agentic"),
    }


@require_super_access_with_host
@login_required
@require_GET
def ai_center_home(request: HttpRequest) -> HttpResponse:
    index = build_platform_index()
    ctx = _cp_context(request, title=_("AI Center"), active="home")
    ctx.update(
        {
            "document_count": index.get("document_count", 0),
            "provider_status": _provider_status(),
        }
    )
    return render(request, "apicenter/super/ai_center_home.html", ctx)


@require_super_access_with_host
@login_required
@require_GET
def ai_center_inventory(request: HttpRequest) -> HttpResponse:
    index = build_platform_index()
    ctx = _cp_context(request, title=_("AI inventory"), active="inventory")
    ctx["index_summary"] = index
    return render(request, "apicenter/super/ai_center_inventory.html", ctx)


@require_super_access_with_host
@login_required
@require_GET
def ai_center_kb_drafts(request: HttpRequest) -> HttpResponse:
    drafts = []
    route = (request.GET.get("route") or "/api-center/").strip()
    try:
        drafts.append(generate_kb_article_from_route(route, audience="operator"))
    except ValueError:
        pass
    ctx = _cp_context(request, title=_("KB drafts"), active="kb_drafts")
    ctx["drafts"] = drafts
    return render(request, "apicenter/super/ai_center_kb_drafts.html", ctx)


@require_super_access_with_host
@login_required
@require_GET
def ai_center_friction(request: HttpRequest) -> HttpResponse:
    topics = friction_topics_for_operator()
    ctx = _cp_context(request, title=_("Friction analysis"), active="friction")
    ctx["topics"] = topics
    ctx["analysis"] = analyze_friction_signals(
        [{"route": t["route"], "module": "platform", "signal": "aggregate", "count": t["friction_score"]} for t in topics]
    )
    return render(request, "apicenter/super/ai_center_friction.html", ctx)


@require_super_access_with_host
@login_required
@require_GET
def ai_center_settings(request: HttpRequest) -> HttpResponse:
    from django.conf import settings as dj_settings

    ctx = _cp_context(request, title=_("AI Center settings"), active="settings")
    ctx["settings_rows"] = [
        ("AI_GATEWAY_ENABLED", getattr(dj_settings, "AI_GATEWAY_ENABLED", False)),
        ("AI_GATEWAY_PROVIDER", getattr(dj_settings, "AI_GATEWAY_PROVIDER", "ollama")),
        ("OLLAMA_MODEL", getattr(dj_settings, "OLLAMA_MODEL", "")),
        ("AI_CENTER_LOG_PROMPTS", getattr(dj_settings, "AI_CENTER_LOG_PROMPTS", False)),
        ("AI_CENTER_MAX_CONTEXT_DOCS", getattr(dj_settings, "AI_CENTER_MAX_CONTEXT_DOCS", 8)),
    ]
    return render(request, "apicenter/super/ai_center_settings.html", ctx)


@require_super_access_with_host
@login_required
@require_http_methods(["GET", "POST"])
def ai_center_query(request: HttpRequest) -> HttpResponse:
    if request.method == "POST" and request.headers.get("X-Requested-With") == "XMLHttpRequest":
        body = json.loads(request.body.decode("utf-8") or "{}")
        question = (body.get("question") or "").strip()
        route = (body.get("route_context") or request.path).strip()
        result = answer_platform_question(
            user=request.user,
            tenant=getattr(request, "school", None),
            role=getattr(request.user, "role", None),
            route_context=route,
            question=question,
            audience="operator",
        )
        return JsonResponse(result.to_dict())
    ctx = _cp_context(request, title=_("AI query"), active="query")
    ctx["sample_hits"] = search_platform_knowledge("api center", limit=5)
    return render(request, "apicenter/super/ai_center_query.html", ctx)


@require_super_access_with_host
@login_required
@require_http_methods(["GET", "POST"])
def ai_center_generate_kb(request: HttpRequest) -> HttpResponse:
    route = (request.GET.get("route") or request.POST.get("route") or "/api-center/").strip()
    draft = None
    error = ""
    if request.method == "POST":
        try:
            draft = generate_kb_article_from_route(route, audience="operator")
        except ValueError as exc:
            error = str(exc)
    ctx = _cp_context(request, title=_("Generate KB draft"), active="generate_kb")
    ctx.update({"route": route, "draft": draft, "error": error})
    return render(request, "apicenter/super/ai_center_generate_kb.html", ctx)


@require_super_access_with_host
@login_required
@require_GET
def ai_center_faq_candidates(request: HttpRequest) -> HttpResponse:
    module = (request.GET.get("module") or "apicenter").strip()
    faqs = generate_faqs_for_module(module)
    faqs += propose_faqs_from_feedback([])
    ctx = _cp_context(request, title=_("FAQ candidates"), active="faq")
    ctx["faqs"] = faqs
    return render(request, "apicenter/super/ai_center_faq_candidates.html", ctx)


@require_super_access_with_host
@login_required
@require_http_methods(["GET", "POST"])
def ai_center_kb_tools(request: HttpRequest) -> HttpResponse:
    """KB authoring tools — generate draft KB / runbook / release-note / help-topic
    content from platform evidence. Drafts are operator-review only and are never
    auto-published to tenants (``tenant_visible`` stays False)."""
    gen = (request.POST.get("gen") or "").strip()
    module = (request.POST.get("module") or request.GET.get("module") or "apicenter").strip()
    feature_key = (request.POST.get("feature_key") or "").strip()
    change_summary = (request.POST.get("change_summary") or "").strip()
    route = (request.POST.get("route") or "").strip()
    error_codes = (request.POST.get("error_codes") or "").strip()
    draft = None
    topics = None
    error = ""
    if request.method == "POST":
        try:
            if gen == "tenant_guide":
                draft = generate_tenant_guide(module, route=route or None)
            elif gen == "operator_runbook":
                draft = generate_operator_runbook(module)
            elif gen == "release_note":
                draft = generate_release_note_from_feature(feature_key or module)
            elif gen == "code_change":
                draft = generate_kb_article_from_code_change(
                    module,
                    change_summary=change_summary or f"Update: {module}",
                    route=route or None,
                )
            elif gen == "help_topics":
                codes = [c.strip() for c in error_codes.split(",") if c.strip()]
                topics = propose_help_topics_from_errors(codes)
            else:
                error = _("Choose a generator.")
        except ValueError as exc:
            error = str(exc)
    ctx = _cp_context(request, title=_("KB authoring tools"), active="kb_tools")
    ctx.update(
        {
            "active_gen": gen,
            "module": module,
            "feature_key": feature_key,
            "change_summary": change_summary,
            "route": route,
            "error_codes": error_codes,
            "draft": draft,
            "topics": topics,
            "error": error,
        }
    )
    return render(request, "apicenter/super/ai_center_kb_tools.html", ctx)


@require_super_access_with_host
@login_required
@require_http_methods(["GET", "POST"])
def ai_center_agentic(request: HttpRequest) -> HttpResponse:
    """Agentic AI — Phase 1 (read-only insights).

    Flag-gated by ``RMC_AI_AGENTIC_ENABLED`` (default off). When on, an operator
    can ask for a read-only insight; the kernel *proposes* matching read-only
    actions, and an explicit Execute runs ONE of them through its bridged runner,
    server-side confirmed and durably audited. No mutating path is reachable here.
    """
    from services import ai_agentic_service as svc
    from services.ai_agentic import ProposedAction

    school = getattr(request, "school", None)
    enabled = svc.agentic_phase1_enabled(school=school)
    actions = svc.available_readonly_actions()

    ctx = _cp_context(request, title=_("Agentic insights"), active="agentic")
    ctx.update(
        {
            "agentic_enabled": enabled,
            "flag_name": "RMC_AI_AGENTIC_ENABLED",
            "readonly_actions": [
                {
                    "name": a.name,
                    "description": a.description,
                    "parameters": list(a.parameters),
                }
                for a in actions
            ],
            "proposals": None,
            "exec_result": None,
            "prompt_text": "",
            "audit_rows": svc.recent_audit(limit=20),
        }
    )

    if request.method == "POST":
        if not enabled:
            ctx["error"] = _("Agentic insights are disabled. Set RMC_AI_AGENTIC_ENABLED to enable.")
            return render(request, "apicenter/super/ai_center_agentic.html", ctx)

        gen = (request.POST.get("gen") or "").strip()
        action_ctx = _build_agentic_ctx(request, school)

        if gen == "propose":
            prompt = (request.POST.get("prompt") or "").strip()
            ctx["prompt_text"] = prompt
            extra = _collect_agentic_params(request)
            proposals = svc.propose(
                prompt=prompt, ctx=action_ctx, school=school, extra_params=extra,
            )
            ctx["proposals"] = [
                {
                    "action": p.action,
                    "params": p.params,
                    "rationale": p.rationale,
                    "confidence": round(p.confidence, 2),
                }
                for p in proposals
            ]
        elif gen == "execute":
            action_name = (request.POST.get("action") or "").strip()
            spec = None
            for a in actions:
                if a.name == action_name:
                    spec = a
                    break
            if spec is None:
                ctx["error"] = _("That action is not a Phase-1 read-only action.")
            else:
                params = {
                    k: (request.POST.get(k) or "").strip()
                    for k in spec.parameters
                    if (request.POST.get(k) or "").strip()
                }
                proposed = ProposedAction(action=action_name, params=params)
                result = svc.execute(
                    proposed=proposed,
                    ctx=action_ctx,
                    confirmed_by_user_id=str(getattr(request.user, "id", "")),
                    school=school,
                )
                ctx["exec_result"] = {
                    "ok": result.ok,
                    "action": result.action,
                    "result": result.result,
                    "error": result.error,
                    "audit_id": result.audit_id,
                    "blocked_reason": result.blocked_reason,
                }
        # Refresh the audit tail to include this attempt.
        ctx["audit_rows"] = svc.recent_audit(limit=20)

    return render(request, "apicenter/super/ai_center_agentic.html", ctx)


def _build_agentic_ctx(request: HttpRequest, school):
    """Build the kernel ActionContext from the authenticated super operator.

    This surface is already super-access gated by ``require_super_access_with_host``;
    the kernel's role check is secondary defense. Super operators carry
    admin-equivalent READ authority, so ADMIN is included alongside their role.
    """
    from services.ai_agentic import ActionContext

    tenant_id = str(getattr(school, "id", "") or "platform")
    user_id = str(getattr(request.user, "id", ""))
    actual_role = str(getattr(request.user, "role", "") or "")
    roles = tuple(r for r in ("ADMIN", actual_role) if r)
    return ActionContext(tenant_id=tenant_id, user_id=user_id, user_roles=roles)


def _collect_agentic_params(request: HttpRequest) -> dict:
    """Pull only the known, safe operator-supplied param fields from POST."""
    allowed = ("class_id", "date_range", "topic", "audience", "locale")
    return {
        k: (request.POST.get(k) or "").strip()
        for k in allowed
        if (request.POST.get(k) or "").strip()
    }


def _provider_status() -> dict:
    try:
        from apps.portal.ai_provider import get_public_ai_provider_status

        return get_public_ai_provider_status()
    except Exception:
        return {"available": False, "label": "unknown"}
