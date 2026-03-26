"""
Sovereign AI: model hub and global upgrade (BR-12 split from super_views).
"""

from __future__ import annotations

import uuid

from django.contrib import messages
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods


def super_ai_gateway_console(request):
    """
    Control plane: one page of JSON POST consoles for every productized /api/ai/* endpoint
    that is not embedded elsewhere (plus shared review-loop feedback).
    """
    return render(
        request,
        "schools/super_ai_gateway_console.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "ai_model_hub_url": reverse("super:ai_model_hub"),
        },
    )


def ai_model_hub(request):
    """
    Super Admin: list regions with default_model, fallback_model, last_health_check_at, status.
    Single source: RegionalAIConfig + health from cache (ai:health:{cluster}).
    """
    from apps.siteconfig.models import RegionalAIConfig
    from apps.siteconfig.tasks import AI_HEALTH_CACHE_PREFIX

    configs = list(
        RegionalAIConfig.objects.filter(is_active=True).order_by("regional_cluster")
    )
    for c in configs:
        health = cache.get(f"{AI_HEALTH_CACHE_PREFIX}{c.regional_cluster}") or {}
        c.health_status = health.get("status", "unknown")
        c.last_health_check_at = health.get("last_check_at", "")

    return render(
        request,
        "schools/super_ai_model_hub.html",
        {
            "configs": configs,
            "dashboard_url": reverse("super:dashboard"),
            "global_ai_version_url": reverse("super:global_ai_version"),
            "ai_gateway_console_url": reverse("super:ai_gateway_console"),
        },
    )


@require_http_methods(["GET", "POST"])
def global_ai_version(request):
    """
    Super Admin: form with target model_id and "Upgrade all regions" button.
    POST enqueues global_ai_upgrade_run and redirects to progress (run_id in session); poll for regions_done/regions_total.
    """
    from apps.siteconfig.models import RegionalAIConfig
    from apps.siteconfig.tasks import global_ai_upgrade_run

    if request.method == "POST":
        model_id = (request.POST.get("model_id") or "").strip()
        if not model_id:
            messages.warning(request, "Model ID is required.")
            return redirect("super:global_ai_version")
        run_id = str(uuid.uuid4())
        global_ai_upgrade_run.delay(run_id, model_id)
        request.session["ai_upgrade_run_id"] = run_id
        return redirect("super:global_ai_version_progress", run_id=run_id)

    clusters = list(
        RegionalAIConfig.objects.filter(is_active=True)
        .values_list("regional_cluster", flat=True)
        .distinct()
    )
    return render(
        request,
        "schools/super_global_ai_version.html",
        {
            "clusters": clusters,
            "dashboard_url": reverse("super:dashboard"),
            "ai_model_hub_url": reverse("super:ai_model_hub"),
        },
    )


def global_ai_version_progress(request, run_id):
    """Poll endpoint or page showing regions_done/regions_total for the run."""
    from apps.siteconfig.tasks import AI_UPGRADE_PROGRESS_PREFIX

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.GET.get(
        "json"
    ):
        data = cache.get(f"{AI_UPGRADE_PROGRESS_PREFIX}{run_id}") or {}
        return JsonResponse(data)
    return render(
        request,
        "schools/super_global_ai_version_progress.html",
        {"run_id": run_id, "dashboard_url": reverse("super:dashboard")},
    )
