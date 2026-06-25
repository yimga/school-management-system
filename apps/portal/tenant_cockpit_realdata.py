"""Tenant role-home cockpit hydration from live school data (v3.90.3)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.portal.tenant_role_home import is_tp_v3_role_home_request

#: Whole-percent scale (ratio → 0..100) for the year-progress bar.
_PERCENT_SCALE = 100


def _parent_widget_bundle(request: HttpRequest) -> dict[str, dict] | None:
    user = getattr(request, "user", None)
    if user is None or str(getattr(user, "role", "") or "").upper() != User.Role.PARENT:
        return None
    try:
        from apps.portal.services import guardian_student_links, parent_dashboard_widget_data

        links = list(guardian_student_links(user, results_only=True))
        students = [link.student for link in links if getattr(link, "student", None)]
        if not students:
            return None
        school = getattr(request, "school", None)
        return parent_dashboard_widget_data(students, school=school)
    except Exception:
        return None


def _teacher_widget_bundle(request: HttpRequest) -> dict[str, dict] | None:
    user = getattr(request, "user", None)
    if user is None or str(getattr(user, "role", "") or "").upper() != User.Role.TEACHER:
        return None
    try:
        from apps.academics.services import get_active_year_and_term
        from apps.portal.services import teacher_dashboard_widget_data, teacher_scope

        year, term = get_active_year_and_term()
        if not year or not term:
            return None
        teacher_profile, assignments, _students, _classrooms = teacher_scope(
            user, academic_year=year
        )
        assignments = list(assignments)
        if teacher_profile is None:
            return None
        raw = teacher_dashboard_widget_data(
            assignments, {}, year, term, teacher=teacher_profile
        )
        attendance = raw.get("attendance") or {}
        return {
            "attendance": {
                "overall": attendance.get("overall"),
                "label": str(_("Class attendance")),
            },
            "finance": {},
            "tasks": raw.get("tasks") or {},
            "performance": {
                "average": raw.get("completion_pct"),
                "label": str(_("Marking completion")),
                "trend": str(_("%(n)s assignments") % {"n": raw.get("assignments_count", 0)}),
            },
        }
    except Exception:
        return None


def _student_widget_bundle(request: HttpRequest) -> dict[str, dict] | None:
    user = getattr(request, "user", None)
    if user is None or str(getattr(user, "role", "") or "").upper() != User.Role.STUDENT:
        return None
    try:
        from apps.communication.models import Message
        from apps.people.models import StudentProfile

        school = getattr(request, "school", None)
        if school is None:
            return None
        profile = (
            StudentProfile.objects.filter(user=user, is_active=True, school=school)
            .select_related("classroom")
            .first()
        )
        unread = Message.objects.filter(
            recipient=user,
            is_read=False,
            school=school,
        ).count()
        class_label = "—"
        if profile and getattr(profile, "classroom", None):
            class_label = profile.classroom.name or "—"
        return {
            "attendance": {"overall": None, "label": str(_("This term"))},
            "finance": {"balance": Decimal("0.00"), "overdue": 0, "label": str(_("Fees"))},
            "tasks": {
                "pending_evaluations": 0,
                "pending_payments": unread,
                "description": str(_("Unread messages")),
            },
            "performance": {"average": None, "label": str(_("Class"))},
            "classroom": {"label": class_label},
        }
    except Exception:
        return None


def _role_widget_bundle(request: HttpRequest) -> dict[str, dict] | None:
    role = str(getattr(getattr(request, "user", None), "role", "") or "").upper()
    if role == User.Role.PARENT:
        return _parent_widget_bundle(request)
    if role == User.Role.TEACHER:
        return _teacher_widget_bundle(request)
    if role == User.Role.STUDENT:
        return _student_widget_bundle(request)
    return None


def _hydrate_today_snapshot(
    request: HttpRequest, section: dict[str, Any], widget_data: dict[str, dict]
) -> dict[str, Any]:
    att = widget_data.get("attendance") or {}
    fin = widget_data.get("finance") or {}
    perf = widget_data.get("performance") or {}
    tasks = widget_data.get("tasks") or {}

    overall = att.get("overall")
    if overall is None:
        overall = 0
    balance = fin.get("balance") or Decimal("0.00")
    overdue = int(fin.get("overdue") or 0)
    pending = int(tasks.get("pending_evaluations") or 0) + int(
        tasks.get("pending_payments") or 0
    )
    avg = perf.get("average")

    cards = [
        {
            "icon": "📊",
            "head": str(_("ATTENDANCE")),
            "value": f"{overall}%" if overall is not None else "—",
            "label": str(att.get("label") or _("This term")),
            "delta_text": "",
            "delta_tone": "success" if overall is not None and overall >= 90 else "",
        },
        {
            "icon": "💳",
            "head": str(_("BALANCE")),
            "value": str(balance),
            "label": str(fin.get("label") or _("Fees")),
            "delta_text": str(_("%(n)s overdue") % {"n": overdue}) if overdue else "",
            "delta_tone": "warn" if overdue else "success",
        },
        {
            "icon": "✓",
            "head": str(_("TASKS")),
            "value": str(pending),
            "label": str(tasks.get("description") or _("Pending items")),
            "delta_text": "",
            "delta_tone": "warn" if pending else "",
        },
    ]
    if avg is not None:
        cards.append(
            {
                "icon": "★",
                "head": str(_("AVERAGE")),
                "value": str(avg),
                "label": str(perf.get("label") or _("Grades")),
                "delta_text": str(perf.get("trend") or ""),
                "delta_tone": "",
            }
        )

    classroom = widget_data.get("classroom") or {}
    class_label = classroom.get("label")
    if class_label and class_label != "—":
        cards.insert(
            0,
            {
                "icon": "🏫",
                "head": str(_("CLASS")),
                "value": str(class_label),
                "label": str(_("Homeroom")),
                "delta_text": "",
                "delta_tone": "",
            },
        )

    child_name = ""
    user = request.user
    if str(getattr(user, "role", "") or "").upper() == User.Role.PARENT:
        from apps.portal.parent_portal_helpers import get_active_child_id
        from apps.portal.services import guardian_student_links

        links = list(guardian_student_links(user, results_only=True))
        students = [link.student for link in links if getattr(link, "student", None)]
        active_id = get_active_child_id(request)
        active = next(
            (s for s in students if s.pk == active_id),
            students[0] if students else None,
        )
        if active is not None:
            child_name = active.get_full_name() or active.first_name or ""

    out = dict(section)
    out["enabled"] = True
    out["live_dot"] = True
    if child_name:
        out["section_label"] = str(_("Today · %(name)s · live") % {"name": child_name})
    else:
        out["section_label"] = str(_("Today · live"))
    if str(getattr(user, "role", "") or "").upper() == User.Role.PARENT:
        try:
            out["switch_link"] = {
                "label": str(_("Switch child →")),
                "url": reverse("portal:parent_dashboard"),
            }
        except Exception:
            out["switch_link"] = {"label": "", "url": ""}
    else:
        out["switch_link"] = {"label": "", "url": ""}
    out["cards"] = cards[:4]
    return out


def _format_widget_event(item: dict[str, Any]) -> dict[str, str | bool] | None:
    """Map parent widget feed rows to cockpit upcoming-events strip schema."""
    if not isinstance(item, dict):
        return None
    if item.get("day") and item.get("title"):
        return {
            "url": item.get("url") or "",
            "day": str(item.get("day") or ""),
            "month": str(item.get("month") or ""),
            "pill_label": str(item.get("pill_label") or ""),
            "pill_tone": item.get("pill_tone") or "",
            "title": str(item.get("title") or ""),
            "meta": str(item.get("meta") or item.get("detail") or ""),
            "is_today": bool(item.get("is_today")),
        }
    when = item.get("when")
    if when is None:
        return None
    if isinstance(when, str):
        try:
            when = datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            return None
    if timezone.is_naive(when):
        when = timezone.make_aware(when, timezone.get_current_timezone())
    local_when = timezone.localtime(when)
    today = timezone.localdate()
    event_day: date = local_when.date()
    days_out = (event_day - today).days
    is_today = days_out == 0
    pill_label = ""
    pill_tone = ""
    if is_today:
        pill_label = str(_("Today"))
        pill_tone = "today"
    elif 0 < days_out <= 7:
        pill_label = str(_("%(n)s days") % {"n": days_out})
        pill_tone = "soon"
    return {
        "url": item.get("url") or "",
        "day": local_when.strftime("%d").lstrip("0") or "0",
        "month": date_format(local_when, "M"),
        "pill_label": pill_label,
        "pill_tone": pill_tone,
        "title": str(item.get("title") or ""),
        "meta": str(item.get("meta") or item.get("detail") or ""),
        "is_today": is_today,
    }


def _hydrate_upcoming_events(
    section: dict[str, Any], widget_data: dict[str, dict]
) -> dict[str, Any]:
    raw_events = widget_data.get("events") or []
    if not raw_events:
        return section
    events = []
    for item in raw_events[:8]:
        if not isinstance(item, dict):
            continue
        formatted = _format_widget_event(item)
        if formatted:
            events.append(formatted)
    if not events:
        return section
    out = dict(section)
    out["enabled"] = True
    out["events"] = events
    return out


def _hydrate_quick_actions(
    request: HttpRequest, section: dict[str, Any]
) -> dict[str, Any]:
    from apps.siteconfig.config_service import get_effective_site_settings
    from apps.siteconfig.models_support import filter_portal_items

    site = get_effective_site_settings(request=request)
    role = str(getattr(request.user, "role", "") or "")
    actions = filter_portal_items(getattr(site, "portal_quick_actions", None) or [], role)
    tiles = []
    for action in actions[:6]:
        tiles.append(
            {
                "url": action.get("url") or "#",
                "icon": (action.get("icon") or "→").replace("bi ", ""),
                "title": str(action.get("label") or ""),
                "sub": "",
                "badge": "",
            }
        )
    if not tiles:
        return section
    out = dict(section)
    out["enabled"] = True
    out["tiles"] = tiles
    return out


def _hydrate_year_progress(
    request: HttpRequest, section: dict[str, Any]
) -> dict[str, Any]:
    """Auto-derive the academic-year progress bar from the active year + term.

    The ``year_progress`` cockpit section ships ``enabled=True`` but with empty
    defaults (``percent=0``, no ``term_label``/``eta_label``), so out of the box
    the bar renders at 0% with no labels — a visible empty state on every admin /
    parent / teacher landing. This overlays live values computed from the active
    ``AcademicYear`` (today's position between its start and end dates) and the
    active ``Term`` label.

    PII-safe: the academic year + term are school-wide calendar markers — no
    student-specific dates ever appear here (same guarantee the section's
    template documents). School-scoped via ``get_active_year_and_term(school=)``.

    Operator override is respected in BOTH directions:
      * ``enabled=False`` (operator opted out)  -> untouched.
      * operator already published a ``term_label`` or non-zero ``percent`` via
        ``SiteSettings.cockpit_payload.year_progress`` -> untouched.
    Degrade-safe: any missing data / malformed dates returns the section as-is.
    """
    if not section.get("enabled"):
        return section
    if section.get("term_label") or section.get("percent"):
        return section
    try:
        from apps.academics.services import get_active_year_and_term

        school = getattr(request, "school", None)
        year, term = get_active_year_and_term(school=school)
    except Exception:
        return section
    if year is None:
        return section
    start = getattr(year, "start_date", None)
    end = getattr(year, "end_date", None)
    if not start or not end:
        return section
    try:
        span_days = (end - start).days
        if span_days <= 0:
            return section
        elapsed_days = (timezone.localdate() - start).days
        percent = max(
            0, min(_PERCENT_SCALE, round(elapsed_days / span_days * _PERCENT_SCALE))
        )
    except (TypeError, ValueError):
        return section

    out = dict(section)
    out["percent"] = percent
    if term is not None:
        term_label = str(getattr(term, "label", "") or "")
        if term_label:
            out["term_label"] = term_label
    try:
        out["eta_label"] = str(
            _("Ends %(date)s") % {"date": year.format_end_date_display()}
        )
    except Exception:
        out["eta_label"] = ""
    return out


def hydrate_year_progress_realdata(
    request: HttpRequest, tenant_cockpit: dict[str, Any]
) -> dict[str, Any]:
    """Overlay live academic-year progress onto the cockpit ``year_progress``.

    Not role-gated — the year-progress bar is a school-wide marker that renders
    on the admin, parent and teacher landings alike, so this runs for every
    tenant cockpit request (unlike the role-home widget hydrators below).
    """
    yp = tenant_cockpit.get("year_progress")
    if isinstance(yp, dict):
        tenant_cockpit["year_progress"] = _hydrate_year_progress(request, yp)
    return tenant_cockpit


def hydrate_role_home_cockpit_realdata(
    request: HttpRequest, tenant_cockpit: dict[str, Any]
) -> dict[str, Any]:
    """Overlay live role-home metrics when demo preview is not forced on."""
    if not is_tp_v3_role_home_request(request):
        return tenant_cockpit
    widget_data = _role_widget_bundle(request)
    if not widget_data:
        return tenant_cockpit

    ts = tenant_cockpit.get("today_snapshot")
    if isinstance(ts, dict):
        tenant_cockpit["today_snapshot"] = _hydrate_today_snapshot(request, ts, widget_data)

    ue = tenant_cockpit.get("upcoming_events")
    if isinstance(ue, dict):
        tenant_cockpit["upcoming_events"] = _hydrate_upcoming_events(ue, widget_data)

    qa = tenant_cockpit.get("quick_actions")
    if isinstance(qa, dict):
        tenant_cockpit["quick_actions"] = _hydrate_quick_actions(request, qa)

    return tenant_cockpit
