"""
Operator UI for KB translation families (batch 1354).
"""

from __future__ import annotations

from collections import defaultdict

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.portal.models_kb import KBArticle
from apps.schools.control_plane import require_control_plane_access
from apps.schools.operator_report_render import render_manager_report_page


@require_http_methods(["GET", "POST"])
@require_control_plane_access
def manager_kb_locale_families(request):
    if request.method == "POST":
        article_id = request.POST.get("article_id")
        group_id = (request.POST.get("locale_group_id") or "").strip()[:36]
        action = (request.POST.get("action") or "").strip()
        article = KBArticle.objects.filter(pk=article_id).first()
        if article and action == "set_group" and group_id:
            article.locale_group_id = group_id
            article.save(update_fields=["locale_group_id"])
            messages.success(request, str(_("Locale group updated.")))
        elif article and action == "mark_canonical":
            if group_id:
                KBArticle.objects.filter(locale_group_id=group_id).exclude(
                    pk=article.pk
                ).update(translation_of=article)
            messages.success(request, str(_("Marked as canonical for group.")))
        return redirect("manager_kb_locale_families")

    groups: dict[str, list[KBArticle]] = defaultdict(list)
    for art in (
        KBArticle.objects.exclude(locale_group_id="")
        .select_related("translation_of")
        .order_by("locale_group_id", "locale", "title")[:500]
    ):
        groups[art.locale_group_id].append(art)

    family_rows = [
        {
            "group_id": gid,
            "articles": arts,
            "locales": sorted({(a.locale or "all") for a in arts}),
        }
        for gid, arts in sorted(groups.items(), key=lambda x: x[0])
    ]

    return render_manager_report_page(
        request,
        body_template="schools/partials/manager_kb_locale_families_body.html",
        context={
            "families": family_rows,
            "help_center_url": reverse("manager_help_center"),
            "kb_home_url": reverse("kb:kb_home"),
        },
        page_title=str(_("KB translation families")),
        page_archetype="operational-workbench",
    )
