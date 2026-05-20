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
    generate_kb_article_from_route,
    propose_faqs_from_feedback,
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


def _provider_status() -> dict:
    try:
        from apps.portal.ai_provider import get_public_ai_provider_status

        return get_public_ai_provider_status()
    except Exception:
        return {"available": False, "label": "unknown"}
