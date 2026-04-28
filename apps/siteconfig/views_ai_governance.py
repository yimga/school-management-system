"""Tenant AI governance summary (no secrets; CP-first)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import permission_required
from apps.compliance.models_audit import AuditLog
from apps.portal.ai_provider import get_public_ai_provider_status
from apps.siteconfig.ai_assistants import iter_assistants, user_may_use_assistant


@login_required
@permission_required("settings.manage")
@require_http_methods(["GET"])
def ai_governance(request: HttpRequest) -> HttpResponse:
    school = getattr(request, "school", None)
    ai_policy: dict = {}
    if school is not None:
        try:
            from apps.policies.policy_registry import get_effective_policy

            raw = get_effective_policy(school) or {}
            ai_policy = raw.get("ai_governance") or {}
        except (AttributeError, ImportError, TypeError, ValueError):
            ai_policy = {}

    provider_status = get_public_ai_provider_status()
    assistant_rows = []
    for row in iter_assistants():
        entry_urls: list[tuple[str, str]] = []
        for name in row.get("entry_url_names") or ():
            try:
                entry_urls.append((name, reverse(name)))
            except NoReverseMatch:
                continue
        assistant_rows.append(
            {
                **row,
                "entry_urls": entry_urls,
                "user_can_open": user_may_use_assistant(
                    request.user, row["required_permission"]
                ),
            }
        )

    audit_feed_url = None
    try:
        audit_feed_url = reverse("ai_copilot_audit")
    except NoReverseMatch:
        pass

    since = timezone.now() - timedelta(days=30)
    ai_audit_recent = 0
    try:
        ai_audit_recent = AuditLog.objects.filter(
            app_label="portal",
            model_name="AICopilot",
            timestamp__gte=since,
        ).count()
    except (AttributeError, TypeError, ValueError):
        pass

    return render(
        request,
        "siteconfig/ai_governance.html",
        {
            "school": school,
            "ai_policy": ai_policy,
            "provider_status": provider_status,
            "assistants": assistant_rows,
            "audit_feed_url": audit_feed_url,
            "ai_audit_recent_count": ai_audit_recent,
        },
    )
