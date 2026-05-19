"""
AI Center — single platform-wide surface for every governed AI assistant.

Replaces the per-page `ai_guided_assistant_card.html` includes that scattered
broken cards across the platform. One place. One chat. All assistants.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.portal.ai_provider import get_public_ai_provider_status
from apps.siteconfig.control_plane_render import (
    default_operator_breadcrumbs,
    operator_cp_breadcrumb,
    render_siteconfig_operator_page,
)
from apps.siteconfig.ai_assistants import (
    get_assistant,
    iter_assistants,
    user_may_use_assistant,
)


def _resolve_optional(url_name: str) -> str | None:
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return None


@login_required
@require_http_methods(["GET"])
def ai_center(request: HttpRequest) -> HttpResponse:
    """Render the AI Center: every assistant, one canonical chat shell."""
    focus_key = (request.GET.get("focus") or request.GET.get("assistant") or "").strip()
    rows = []
    default_row = None
    for row in iter_assistants():
        api_url = _resolve_optional(row.get("api_url_name") or "")
        entry_urls = []
        for name in row.get("entry_url_names") or ():
            url = _resolve_optional(name)
            if url:
                entry_urls.append({"name": name, "url": url})
        usable = user_may_use_assistant(request.user, row["required_permission"])
        enriched = {
            **row,
            "api_url": api_url,
            "entry_urls": entry_urls,
            "user_can_open": usable,
            "is_ready": bool(api_url) and usable,
        }
        rows.append(enriched)
        if focus_key and row["assistant_key"] == focus_key and enriched["is_ready"]:
            default_row = enriched

    if default_row is None:
        for row in rows:
            if row["is_ready"]:
                default_row = row
                break

    user = request.user
    show_operator_setup = bool(
        getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)
    )
    return render_siteconfig_operator_page(
        request,
        portal_template="siteconfig/ai_center.html",
        body_template="siteconfig/partials/ai_center_body.html",
        context={
            "assistants": rows,
            "default_assistant": default_row,
            "provider_status": get_public_ai_provider_status(),
            "ai_governance_url": _resolve_optional("siteconfig:ai_governance"),
            "help_center_url": _resolve_optional("feedback:help_center"),
            "ai_feedback_url": _resolve_optional("api:ai-feedback"),
            "show_operator_ollama_setup": show_operator_setup,
        },
        cp_title=_("AI Center"),
        breadcrumbs=default_operator_breadcrumbs(
            operator_cp_breadcrumb(_("AI Center"), active=True),
            include_config_center=True,
        ),
    )
