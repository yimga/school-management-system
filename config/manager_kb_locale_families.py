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

from apps.portal.kb_locale_ops import (
    LOCALE_VARIANT_TARGETS,
    create_locale_variant,
    ensure_locale_variants_for_group,
    publish_locale_article,
    publish_locale_group,
)
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
        elif article and action == "create_variant":
            locale = (request.POST.get("locale") or "").strip().lower()
            try:
                variant = create_locale_variant(
                    article, locale=locale, author=request.user
                )
                messages.success(
                    request,
                    str(_("Draft variant: %(slug)s") % {"slug": variant.slug}),
                )
            except ValueError:
                messages.error(request, str(_("Locale is required.")))
        elif article and action == "seed_variants":
            created = ensure_locale_variants_for_group(article, author=request.user)
            messages.success(
                request,
                str(_("Created %(n)s locale drafts.") % {"n": len(created)}),
            )
        elif article and action == "publish_one":
            publish_locale_article(article, author=request.user)
            messages.success(
                request,
                str(_("Published: %(title)s") % {"title": article.title[:80]}),
            )
        elif action == "publish_group" and group_id:
            anchor = (
                KBArticle.objects.filter(pk=article_id).first()
                if article_id
                else None
            )
            n = publish_locale_group(
                group_id,
                author=request.user,
                school_id=anchor.school_id if anchor else None,
            )
            messages.success(
                request, str(_("Published %(n)s articles in group.") % {"n": n})
            )
        return redirect("manager_kb_locale_families")

    groups: dict[str, list[KBArticle]] = defaultdict(list)
    for art in (
        KBArticle.objects.exclude(locale_group_id="")
        .select_related("translation_of")
        .order_by("locale_group_id", "locale", "title")[:500]
    ):
        groups[art.locale_group_id].append(art)

    family_rows = []
    for gid, arts in sorted(groups.items(), key=lambda x: x[0]):
        existing_locales = {
            (a.locale or "").lower()
            for a in arts
            if (a.locale or "").strip()
        }
        family_rows.append(
            {
                "group_id": gid,
                "articles": arts,
                "locales": sorted({(a.locale or "all") for a in arts}),
                "missing_locales": [
                    loc for loc in LOCALE_VARIANT_TARGETS if loc not in existing_locales
                ],
            }
        )

    return render_manager_report_page(
        request,
        body_template="schools/partials/manager_kb_locale_families_body.html",
        context={
            "families": family_rows,
            "help_center_url": reverse("manager_help_center"),
            "kb_home_url": reverse("kb:kb_home"),
            "docs_hub_url": reverse("kb:kb_docs_hub"),
            "locale_targets": LOCALE_VARIANT_TARGETS,
        },
        page_title=str(_("KB translation families")),
        page_archetype="operational-workbench",
    )
