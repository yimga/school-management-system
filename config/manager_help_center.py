"""
Operator Help Center hub — single front door for support surfaces on manager host.

Help Center is NOT the same as the Knowledge Base: KB is one card among many
(product matrix, feature gaps, feedback loop, AI center, FAQ, documentation).
"""

from __future__ import annotations

from django.contrib import messages
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.feedback.form_widgets import apply_bootstrap_form_styles
from apps.feedback.db_readiness import (
    feature_request_queryset,
    feedback_schema_ready,
    open_feature_request_count,
)
from apps.feedback.forms import FeatureRequestForm
from apps.feedback.services import submit_feature_request, support_entry_points
from apps.schools.control_plane import require_control_plane_access
from apps.portal.help_page_inbound import feature_form_initial_from_request, parse_help_landing_inbound
from apps.portal.help_unified_hub import operator_public_kb_lane
from apps.schools.operator_help_signals import operator_help_signal_bundle
from apps.portal.help_section_nav import manager_help_section_nav_items
from apps.schools.operator_report_render import render_manager_report_page


def _link(url_name: str, **kwargs) -> str | None:
    try:
        return reverse(url_name, kwargs=kwargs)
    except NoReverseMatch:
        return None


def _engage_actions() -> list[dict]:
    """Primary customer-voice CTAs — always visible above the fold."""
    actions = [
        {
            "id": "request-feature",
            "title": _("Request a feature"),
            "description": _(
                "Describe a workflow gap or capability your schools need — triage reviews every request."
            ),
            "icon": "bi-lightbulb-fill",
            "accent": "primary",
            "url": _link("manager_feature_center"),
            "cta": _("Open feature center"),
        },
        {
            "id": "public-kb",
            "title": _("Public help corpus"),
            "description": _(
                "Sovereign marketing KB — featured runbooks and semantic search on runmycampus.com."
            ),
            "icon": "bi-globe2",
            "accent": "success",
            "url": _link("marketing_kb_search"),
            "cta": _("Search public KB"),
        },
        {
            "id": "help-analytics",
            "title": _("Help analytics"),
            "description": _(
                "North-star deflection, CSAT, zero-result gaps, and exportable metrics."
            ),
            "icon": "bi-graph-up-arrow",
            "accent": "info",
            "url": _link("manager_help_analytics"),
            "cta": _("Open analytics"),
        },
        {
            "id": "contact-us",
            "title": _("Contact us"),
            "description": _(
                "Route to platform support, product feedback, or public contact lanes."
            ),
            "icon": "bi-chat-dots-fill",
            "accent": "secondary",
            "url": _link("manager_contact_us"),
            "cta": _("Contact options"),
        },
        {
            "id": "support-request",
            "title": _("Urgent support"),
            "description": _(
                "Login, billing, imports, or production blockers — open an operational ticket."
            ),
            "icon": "bi-life-preserver",
            "accent": "danger",
            "url": _link("manager_support_request"),
            "cta": _("Open support request"),
        },
    ]
    return [a for a in actions if a.get("url")]


def _help_center_sections() -> list[dict]:
    """Grouped navigation — discover, engage, operate, govern."""

    def card(title, description, icon, url_name, **kwargs):
        return {
            "title": title,
            "description": description,
            "icon": icon,
            "url": _link(url_name, **kwargs),
        }

    sections = [
        {
            "id": "discover",
            "title": _("Discover & learn"),
            "description": _("Docs, AI, and self-serve answers."),
            "cards": [
                card(
                    _("Knowledge base"),
                    _("Guides, tutorials, and step-by-step operator runbooks."),
                    "bi-journal-text",
                    "kb:kb_home",
                ),
                card(
                    _("FAQ"),
                    _("Quick answers to common operator and platform questions."),
                    "bi-patch-question",
                    "kb:faq_list",
                ),
                card(
                    _("AI Center"),
                    _("Governed assistants — ask questions grounded in platform docs."),
                    "bi-stars",
                    "siteconfig:ai_center",
                ),
                card(
                    _("KB draft factory"),
                    _(
                        "Code-aware KB drafts from platform routes — human review before publish."
                    ),
                    "bi-robot",
                    "super:ai_center_kb_drafts",
                ),
                card(
                    _("Generate how-tos from code"),
                    _("Scan platform routes and emit draft operator runbooks."),
                    "bi-magic",
                    "super:ai_center_generate_kb",
                ),
                card(
                    _("FAQ candidates"),
                    _("AI-suggested FAQ entries from support friction signals."),
                    "bi-patch-question-fill",
                    "super:ai_center_faq_candidates",
                ),
                card(
                    _("My documentation"),
                    _("Account docs, release notes, and operator quick links."),
                    "bi-folder2-open",
                    "accounts:user_documentation",
                ),
                card(
                    _("Office documents"),
                    _("Collabora-hosted runbooks when configured."),
                    "bi-file-earmark-word",
                    "kb:office_document_list",
                ),
                card(
                    _("What's new"),
                    _("Public release notes and changelog."),
                    "bi-stars",
                    "feedback:release_notes_public",
                ),
            ],
        },
        {
            "id": "engage",
            "title": _("Engage & influence product"),
            "description": _("Request capabilities, vote priority, and track outcomes."),
            "cards": [
                card(
                    _("Feature center"),
                    _("Submit feature requests, signal priority, and see roadmap candidates."),
                    "bi-lightbulb",
                    "manager_feature_center",
                ),
                card(
                    _("Product roadmap"),
                    _("What we are building, piloting, and releasing."),
                    "bi-map",
                    "manager_product_roadmap",
                ),
                card(
                    _("Voice of customer"),
                    _("Cross-tenant feedback triage and conversion to features."),
                    "bi-megaphone",
                    "feedback:voice_of_customer",
                ),
                card(
                    _("Contact us"),
                    _("Choose the right lane: support, product voice, or public contact."),
                    "bi-envelope-heart",
                    "manager_contact_us",
                ),
            ],
        },
        {
            "id": "operate",
            "title": _("Operate & respond"),
            "description": _("Live signals and operator feedback."),
            "cards": [
                card(
                    _("Help analytics"),
                    _("Deflection rate, CSAT, content gaps, and weekly CSV export."),
                    "bi-graph-up",
                    "manager_help_analytics",
                ),
                card(
                    _("AI review queue"),
                    _("Failed support AI sessions — resolve, draft, and publish KB."),
                    "bi-shield-check",
                    "manager_ai_review_queue",
                ),
                card(
                    _("Feedback loop · live usage"),
                    _("Friction, feedback submissions, and AI adoption (7d/30d)."),
                    "bi-activity",
                    "manager_feedback_loop",
                ),
                card(
                    _("Platform support queue"),
                    _("Structured support requests with SLA tracking."),
                    "bi-ticket-detailed",
                    "manager_support_request",
                ),
            ],
        },
        {
            "id": "govern",
            "title": _("Govern & prove"),
            "description": _("Readiness registers and public promise tracking."),
            "cards": [
                card(
                    _("Public → product matrix"),
                    _("What we promise publicly vs what is demonstrably wired."),
                    "bi-grid-3x3-gap",
                    "manager_public_to_product_matrix",
                ),
                card(
                    _("Feature gap register"),
                    _("Shipped features must resolve a proof route, model, or gate."),
                    "bi-list-check",
                    "manager_feature_gap_register",
                ),
                card(
                    _("Lane-2 readiness"),
                    _("PSP adapters, SOC2 controls, and pilot tracker for commercial work."),
                    "bi-speedometer2",
                    "manager_lane2_readiness",
                ),
            ],
        },
    ]
    for section in sections:
        section["cards"] = [c for c in section["cards"] if c.get("url")]
    return [s for s in sections if s["cards"]]


@require_http_methods(["GET", "POST"])
@require_control_plane_access
def manager_help_center(request):
    signals = operator_help_signal_bundle()
    kb_search_url = _link("kb:kb_search")
    support_links = support_entry_points(request)
    page_help_inbound = parse_help_landing_inbound(request)

    feature_quick_form = FeatureRequestForm(
        initial=feature_form_initial_from_request(
            request,
            {
                "module": request.GET.get("module", ""),
                "title": request.GET.get("title", ""),
                "affected_roles": "ADMIN,TEACHER",
            },
        )
    )
    apply_bootstrap_form_styles(feature_quick_form)
    if request.method == "POST" and request.POST.get("form_kind") == "feature_quick":
        feature_quick_form = FeatureRequestForm(request.POST)
        apply_bootstrap_form_styles(feature_quick_form)
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
            from django.shortcuts import redirect

            return redirect("manager_help_center")
        if feature_quick_form.is_valid():
            submit_feature_request(
                school=None,
                user=request.user,
                affected_roles=[
                    r.strip().upper()
                    for r in feature_quick_form.cleaned_data["affected_roles"].split(",")
                    if r.strip()
                ],
                **{
                    k: v
                    for k, v in feature_quick_form.cleaned_data.items()
                    if k != "affected_roles"
                },
            )
            messages.success(
                request,
                str(
                    _(
                        "Feature request received. Track it in Feature center or Voice of customer."
                    )
                ),
            )
            from django.shortcuts import redirect

            return redirect("manager_help_center")

    recent_features = list(
        feature_request_queryset()
        .filter(submitted_by=request.user)
        .order_by("-created_at")[:5]
    )

    help_sections = _help_center_sections()
    return render_manager_report_page(
        request,
        body_template="schools/partials/manager_help_center_body.html",
        context={
            "help_sections": help_sections,
            "help_section_nav_items": manager_help_section_nav_items(
                help_sections,
                include_featured=bool((signals.get("kb") or {}).get("featured")),
            ),
            "engage_actions": _engage_actions(),
            "signals": signals,
            "kb_search_url": kb_search_url,
            "feedback_loop_url": _link("manager_feedback_loop"),
            "support_links": support_links,
            "feature_quick_form": feature_quick_form,
            "recent_features": recent_features,
            "open_feature_count": open_feature_request_count(),
            "feedback_schema_pending": not feedback_schema_ready(),
            "feature_center_url": _link("manager_feature_center"),
            "contact_us_url": _link("manager_contact_us"),
            "ai_review_url": _link("manager_ai_review_queue"),
            "analytics_url": _link("manager_help_analytics"),
            "public_kb_lane": operator_public_kb_lane(),
            **page_help_inbound,
        },
        page_title=str(_("Help center")),
        page_archetype="decision-console",
    )
