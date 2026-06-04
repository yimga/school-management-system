"""
Manager-host customer voice surfaces — feature requests, contact routing, roadmap.

Wrapped in control-plane chrome (render_manager_report_page). Tenant schools use
apps.feedback.views on tenant hosts; operators use these routes on manager.runmycampus.com.
"""

from __future__ import annotations

from django.contrib import messages
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.feedback.form_widgets import apply_bootstrap_form_styles
from apps.feedback.db_readiness import (
    feature_request_queryset,
    feedback_schema_ready,
    open_feature_request_count,
    roadmap_queryset,
)
from apps.feedback.forms import FeatureRequestForm
from apps.feedback.services import (
    generate_you_said_we_did_items,
    submit_feature_request,
    support_entry_points,
    visible_roadmap_for_user,
)
from apps.schools.control_plane import require_control_plane_access
from apps.schools.operator_report_render import render_manager_report_page


@require_http_methods(["GET", "POST"])
@require_control_plane_access
def manager_feature_center(request):
    """Operator feature discovery — submit requests and review cross-tenant signals."""
    if request.method == "POST":
        form = FeatureRequestForm(request.POST)
        if not feedback_schema_ready():
            messages.warning(
                request,
                str(
                    _(
                        "Feature requests are temporarily unavailable while database "
                        "migrations finish. Try again shortly or contact platform support."
                    )
                ),
            )
            return redirect_manager_feature_center()
        if form.is_valid():
            submit_feature_request(
                school=None,
                user=request.user,
                affected_roles=[
                    r.strip().upper()
                    for r in form.cleaned_data["affected_roles"].split(",")
                    if r.strip()
                ],
                **{k: v for k, v in form.cleaned_data.items() if k != "affected_roles"},
            )
            messages.success(
                request,
                str(_("Feature request submitted — product triage will review it.")),
            )
            return redirect_manager_feature_center()
    else:
        form = FeatureRequestForm(
            initial={
                "module": request.GET.get("module", ""),
                "title": request.GET.get("title", ""),
                "affected_roles": "ADMIN,TEACHER",
            }
        )
        apply_bootstrap_form_styles(form)

    feature_requests = list(
        feature_request_queryset()
        .select_related("school", "submitted_by")
        .order_by("-weighted_score", "-created_at")[:75]
    )
    return render_manager_report_page(
        request,
        body_template="schools/partials/manager_feature_center_body.html",
        context={
            "feature_form": form,
            "feature_requests": feature_requests,
            "feedback_schema_pending": not feedback_schema_ready(),
            "roadmap_items": list(
                roadmap_queryset()
                .filter(tenant_visibility=True)
                .order_by("-priority_score")[:30]
            ),
            "you_said_we_did": generate_you_said_we_did_items(None)[:10],
            "support_links": support_entry_points(request),
            "help_center_url": reverse("manager_help_center"),
        },
        page_title=str(_("Request a feature")),
        page_archetype="operational-workbench",
    )


@require_http_methods(["GET"])
@require_control_plane_access
def manager_contact_us(request):
    """Operator contact router — platform support, product voice, and public contact."""
    links = support_entry_points(request)
    return render_manager_report_page(
        request,
        body_template="schools/partials/manager_contact_us_body.html",
        context={
            "support_links": links,
            "open_feature_count": open_feature_request_count(),
            "feedback_schema_pending": not feedback_schema_ready(),
            "help_center_url": reverse("manager_help_center"),
            "manager_support_url": reverse("manager_support_request"),
        },
        page_title=str(_("Contact us")),
        page_archetype="contact-routing",
    )


@require_http_methods(["GET"])
@require_control_plane_access
def manager_product_roadmap(request):
    """Public + tenant-visible roadmap for operators."""
    return render_manager_report_page(
        request,
        body_template="schools/partials/manager_product_roadmap_body.html",
        context={
            "roadmap_items": visible_roadmap_for_user(request.user, None),
            "support_links": support_entry_points(request),
            "help_center_url": reverse("manager_help_center"),
        },
        page_title=str(_("Product roadmap")),
        page_archetype="decision-console",
    )


def redirect_manager_feature_center():
    from django.shortcuts import redirect

    return redirect("manager_feature_center")
