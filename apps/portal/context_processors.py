"""
Context processors for portal app.
"""

from django.db import DatabaseError, connection, transaction
from django.db.transaction import TransactionManagementError
from django.db.models import Q
from django.utils import timezone

from .models import Announcement


def platform_status_strip(request):
    """
    Public-safe active incident summary for tenant portal shells (cached ~60s).
    """
    try:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return {"platform_status_strip": {"show": False}}
        school = getattr(request, "school", None)
        school_id = getattr(school, "pk", None) if school is not None else None
        from apps.observability.tenant_public_status import (
            compute_platform_status_strip_bundle,
        )

        return {
            "platform_status_strip": compute_platform_status_strip_bundle(school_id)
        }
    except (DatabaseError, TransactionManagementError):
        _reset_db_state()
        return {"platform_status_strip": {"show": False}}


def _reset_db_state() -> None:
    """Reset a broken transaction after a handled DB error."""
    try:
        if connection.in_atomic_block:
            transaction.set_rollback(False)
        else:
            connection.rollback()
    except (DatabaseError, TransactionManagementError):
        pass


def announcements(request):
    """
    Context processor to pass active announcements to all templates.
    """
    try:
        if connection.needs_rollback:
            _reset_db_state()
            return {"announcements": []}
        now = timezone.now()
        active_announcements = (
            # tenant-isolation-allow: context-scoped-via-request-school-membership
            Announcement.objects.filter(is_active=True)
            .filter(
                Q(start_date__isnull=True) | Q(start_date__lte=now),
                Q(end_date__isnull=True) | Q(end_date__gte=now),
            )
            .values("id", "title", "message", "banner_type")
        )
        return {"announcements": list(active_announcements)}
    except (DatabaseError, TransactionManagementError):
        _reset_db_state()
        return {"announcements": []}


def support_deflection_urls(request):
    """Universal deflection API URLs for ticket-like forms (batch 1347)."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    try:
        from django.urls import reverse

        return {
            "support_deflection_url": reverse("api:support-deflection"),
            "support_deflection_ack_url": reverse("api:support-deflection-ack"),
        }
    except Exception:
        return {}


def help_contextual(request):
    """Proactive nudges + contextual help drawer (batches 1346/1352/1353)."""
    from apps.portal.help_proactive_inline import (
        module_inline_assistant_for_request,
        proactive_nudge_for_request,
    )
    from apps.portal.school_help_context import contextual_help_drawer_enabled

    nudge = proactive_nudge_for_request(request)
    inline_assistant = module_inline_assistant_for_request(request)
    drawer = contextual_help_drawer_enabled(request)
    journey = None
    journey_articles: list = []
    if drawer:
        try:
            from apps.portal.help_guided_journeys import (
                journey_for_path,
                resolve_journey_articles,
            )
            from apps.portal.kb_context import is_operator_help_request

            path = getattr(request, "path", "")
            operator = is_operator_help_request(request)
            journey = journey_for_path(path, operator=operator)
            journey_articles = resolve_journey_articles(
                school=getattr(request, "school", None),
                path=path,
                operator=operator,
            )
        except Exception:
            journey = None
            journey_articles = []
    urls: dict[str, str] = {}
    if drawer or nudge:
        try:
            from django.urls import reverse

            urls = {
                "help_center_url": reverse("feedback:help_center"),
                "kb_home_url": reverse("kb:kb_home"),
            }
            if getattr(request, "public_host_kind", None) == "manager":
                urls["help_center_url"] = reverse("manager_help_center")
        except Exception:
            pass
    proactive_tenant: list = []
    try:
        from apps.portal.tenant_proactive_suggestions import proactive_suggestions_for_request

        proactive_tenant = proactive_suggestions_for_request(request)
    except Exception:
        proactive_tenant = []

    return {
        "proactive_help_nudge": nudge,
        "proactive_tenant_suggestions": proactive_tenant,
        "show_contextual_help_drawer": drawer,
        "help_guided_journey": journey,
        "help_guided_journey_articles": journey_articles,
        "help_contextual_urls": urls,
        **inline_assistant,
    }


def help_ai_governance(request):
    """Parent/student AI policy flags for templates (batch GEOS-AI)."""
    from apps.portal.help_governance import (
        ai_assistant_panel_enabled_for_request,
        parent_student_help_surface_policy,
    )

    return {
        "show_kb_ai_assistant_panel": ai_assistant_panel_enabled_for_request(request),
        "parent_student_help_policy": parent_student_help_surface_policy(),
    }
