"""
Operator HITL queue for failed support AI interactions (batch 1340).
"""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.feedback.models import SupportAIInteractionReview
from apps.schools.control_plane import require_control_plane_access
from apps.schools.operator_report_render import render_manager_report_page


@require_http_methods(["GET", "POST"])
@require_control_plane_access
def manager_ai_review_queue(request):
    pending_qs = SupportAIInteractionReview.objects.filter(
        status=SupportAIInteractionReview.Status.PENDING
    ).select_related("school", "user", "kb_draft_article").order_by("-created_at")
    pending_count = pending_qs.count()
    pending = list(pending_qs[:100])

    if request.method == "POST":
        review_id = request.POST.get("review_id")
        action = (request.POST.get("action") or "").strip()
        note = (request.POST.get("note") or "").strip()[:500]
        row = SupportAIInteractionReview.objects.filter(pk=review_id).first()
        if row and action == "publish_kb_draft":
            try:
                from apps.portal.kb_hitl_publish import create_kb_draft_from_review

                article = create_kb_draft_from_review(row, author=request.user)
                messages.success(
                    request,
                    str(_("KB draft created: %(slug)s") % {"slug": article.slug}),
                )
            except Exception as exc:
                messages.error(request, str(_("Could not create KB draft: %(e)s") % {"e": exc}))
            return redirect("manager_ai_review_queue")
        if row and action == "publish_kb" and row.kb_draft_article_id:
            from apps.portal.kb_hitl_publish import publish_kb_article

            article = publish_kb_article(row.kb_draft_article, author=request.user)
            messages.success(
                request,
                str(_("Published: %(slug)s") % {"slug": article.slug}),
            )
            return redirect("manager_ai_review_queue")
        if row and action in ("resolve", "dismiss"):
            from django.utils import timezone

            row.status = (
                SupportAIInteractionReview.Status.RESOLVED
                if action == "resolve"
                else SupportAIInteractionReview.Status.DISMISSED
            )
            row.note = note
            row.resolved_at = timezone.now()
            row.save(update_fields=["status", "note", "resolved_at"])
            messages.success(request, str(_("Review updated.")))
        return redirect("manager_ai_review_queue")

    return render_manager_report_page(
        request,
        body_template="schools/partials/manager_ai_review_queue_body.html",
        context={
            "pending_reviews": pending,
            "pending_count": pending_count,
            "kb_home_url": reverse("kb:kb_home"),
            "help_center_url": reverse("manager_help_center"),
            "analytics_url": reverse("manager_help_analytics"),
        },
        page_title=str(_("AI review qu