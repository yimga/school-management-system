"""
Operator Help Center hub — single front door for support surfaces on manager host.

Help Center is NOT the same as the Knowledge Base: KB is one card among many
(product matrix, feature gaps, feedback loop, AI center, FAQ, documentation).
"""

from __future__ import annotations

from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET

from apps.schools.control_plane import require_control_plane_access
from apps.schools.operator_help_signals import operator_help_signal_bundle
from apps.schools.operator_report_render import render_manager_report_page


def _link(url_name: str, **kwargs) -> str | None:
    try:
        return reverse(url_name, kwargs=kwargs)
    except NoReverseMatch:
        return None


def _help_center_sections() -> list[dict]:
    """Grouped navigation — discover, operate, govern."""
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
            ],
        },
        {
            "id": "operate",
            "title": _("Operate & respond"),
            "description": _("Live signals and operator feedback."),
            "cards": [
                card(
                    _("Feedback loop · live usage"),
                    _("Friction, feedback submissions, and AI adoption (7d/30d)."),
                    "bi-activity",
                    "manager_feedback_loop",
                ),
                card(
                    _("Contact support"),
                    _("Open the feedback loop dashboard or submit operator feedback."),
                    "bi-envelope",
                    "manager_feedback_loop",
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


@require_GET
@require_control_plane_access
def manager_help_center(request):
    signals = operator_help_signal_bundle()
    kb_search_url = _link("kb:kb_search")

    return render_manager_report_page(
        request,
        body_template="schools/partials/manager_help_center_body.html",
        context={
            "help_sections": _help_center_sections(),
            "signals": signals,
            "kb_search_url": kb_search_url,
            "feedback_loop_url": _link("manager_feedback_loop"),
        },
        page_title=str(_("Help center")),
        page_archetype="decision-console",
    )
