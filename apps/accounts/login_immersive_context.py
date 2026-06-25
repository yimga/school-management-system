"""Anonymous login page immersive canvas — ticker, carousel, moments, dash feed."""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def _safe_student_count(school: Any) -> int | None:
    if not school:
        return None
    try:
        from apps.people.models import StudentProfile

        return StudentProfile.objects.filter(school=school, is_active=True).count()
    except Exception:
        return None


def _carousel_slides(site: Any, *, is_manager: bool) -> list[dict[str, str]]:
    if is_manager:
        return [
            {
                "eyebrow": str(_("Platform")),
                "title": str(_("One console for every school, tenant, and operator workflow.")),
                "body": str(_("Manage provisioning, billing, and support from a single surface.")),
            },
            {
                "eyebrow": str(_("Security")),
                "title": str(_("Audit-ready operations with tenant isolation by default.")),
                "body": str(_("Every action is scoped to the school you are serving.")),
            },
        ]
    hero = getattr(site, "login_hero_subtext", None) or getattr(site, "tagline", None)
    site_name = getattr(site, "site_name", None) or _("your school")
    return [
        {
            "eyebrow": str(_("Portal")),
            "title": str(
                _("Attendance, marks, fees, and messages — one secure place for staff and families.")
            ),
            "body": str(
                _("Sign in with your school email to reach the workspace for %(school)s.")
            )
            % {"school": site_name},
        },
        {
            "eyebrow": str(_("Families")),
            "title": str(_("Report cards and fee balances the same day they post.")),
            "body": str(_("Parents see updates without waiting for paper slips or phone calls.")),
        },
        {
            "eyebrow": str(_("Staff")),
            "title": str(_("Gradebook, attendance, and announcements in one calm workspace.")),
            "body": str(hero or _("Everything your team needs during the school day.")),
        },
    ]


def _ticker_items(section: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for card in section.get("cards") or []:
        if not isinstance(card, dict):
            continue
        text = str(card.get("text") or "").strip()
        if text:
            items.append(text)
    for ann in section.get("announcements") or []:
        if not isinstance(ann, dict):
            continue
        text = str(ann.get("text") or "").strip()
        if text and text not in items:
            items.append(text)
    return items[:12]


def _dash_feed(section: dict[str, Any]) -> list[dict[str, str]]:
    feed: list[dict[str, str]] = []
    for card in (section.get("cards") or [])[:5]:
        if not isinstance(card, dict):
            continue
        text = str(card.get("text") or "").strip()
        if not text:
            continue
        severity = str(card.get("severity") or "info").lower()
        tag = _("New")
        tag_class = "warn"
        if severity in {"danger", "critical"}:
            tag = _("Urgent")
            tag_class = "warn"
        elif severity in {"success", "ok"}:
            tag = _("Update")
            tag_class = "ok"
        elif severity in {"info", "neutral"}:
            tag = _("Info")
            tag_class = "info"
        icon = str(card.get("icon") or "📢").strip() or "📢"
        feed.append(
            {
                "icon": icon,
                "title": text.split("·")[0].strip()[:80],
                "subtitle": text if "·" in text else "",
                "tag": str(tag),
                "tag_class": tag_class,
            }
        )
    if not feed:
        feed = [
            {
                "icon": "📢",
                "title": str(_("Welcome to your school portal")),
                "subtitle": str(_("Sign in to see live announcements here.")),
                "tag": str(_("Portal")),
                "tag_class": "info",
            }
        ]
    return feed


def _moment_gallery(request: Any, wallpaper_url: str) -> list[dict[str, str]]:
    from django.templatetags.static import static

    defaults = [
        {
            "url": static("images/marketing/platform-teacher-workspace.svg"),
            "caption": str(_("Teacher workspace")),
        },
        {
            "url": static("images/marketing/platform-parent-mobile-portal.svg"),
            "caption": str(_("Family portal")),
        },
        {
            "url": static("images/marketing/platform-student-self-service.svg"),
            "caption": str(_("Student hub")),
        },
    ]
    if wallpaper_url:
        defaults[0] = {"url": wallpaper_url, "caption": str(_("Campus"))}
    return defaults


def build_login_immersive_context(request: Any) -> dict[str, Any]:
    """Build template-safe immersive login payload (anonymous-safe reads only)."""
    is_manager = getattr(request, "public_host_kind", None) == "manager"
    school = getattr(request, "school", None)
    site = None
    wallpaper = ""
    try:
        from apps.platform_runtime.helpers import get_effective_site_settings

        site = get_effective_site_settings(request=request, school=school)
    except Exception:
        site = None

    try:
        from apps.siteconfig.context_processors import site_settings

        ctx = site_settings(request)
        wallpaper = (ctx.get("TENANT_WALLPAPER_URL") or "").strip()
    except Exception:
        wallpaper = ""

    ticker_section: dict[str, Any] = {"cards": [], "announcements": []}
    try:
        from apps.siteconfig.cockpit_context import _resolve_cockpit_payload
        from apps.siteconfig.cockpit_live_banner_program import finalize_live_banner_section

        payload = _resolve_cockpit_payload(request)
        if is_manager:
            ticker_section = dict(payload.get("activity_ticker") or {})
        else:
            ticker_section = dict(payload.get("tenant_activity_ticker") or {})
        ticker_section = finalize_live_banner_section(ticker_section, request)
    except Exception:
        pass

    now = timezone.localtime(timezone.now())
    student_count = _safe_student_count(school)
    bento = [
        {
            "label": str(_("Students")),
            "value": str(student_count) if student_count is not None else "—",
            "sub": str(_("Enrolled")) if student_count is not None else str(_("Live data after sign-in")),
        },
        {
            "label": str(_("Today")),
            "value": now.strftime("%a"),
            "sub": now.strftime("%b %d"),
        },
        {
            "label": str(_("Portal")),
            "value": str(_("Secure")),
            "sub": str(_("Encrypted sign-in")),
        },
        {
            "label": str(_("Support")),
            "value": str(_("Help")),
            "sub": str(_("Office or IT desk")),
        },
    ]

    return {
        "ticker_items": _ticker_items(ticker_section) or [
            str(_("Welcome — sign in to reach your school workspace."))
        ],
        "carousel_slides": _carousel_slides(site, is_manager=is_manager),
        "bento_stats": bento,
        "dash_feed": _dash_feed(ticker_section),
        "moments": _moment_gallery(request, wallpaper),
        "clock_label": now.strftime("%H:%M"),
        "date_label": now.strftime("%a, %b %d"),
    }
