"""v4.00.43 — Support on-call rotation operator UI."""

from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_TEAM_MANAGE,
    PLATFORM_SCOPE_TEAM_READ,
    require_platform_scope,
)


def _parse_dt(raw: str):
    if not raw:
        return None
    dt = parse_datetime(raw)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


@require_platform_scope(PLATFORM_SCOPE_TEAM_READ)
def support_on_call_dashboard(request):
    """List active + upcoming on-call shifts and offer an inline add form."""
    from apps.accounts.models import User
    from apps.siteconfig.models_feature_controls import SupportOnCallShift
    from apps.siteconfig.support_on_call import (
        get_active_backup_users,
        get_active_on_call_user,
    )

    now = timezone.now()
    horizon = now + timedelta(days=30)
    upcoming = list(
        SupportOnCallShift.objects.select_related("user")
        .filter(ends_at__gt=now, starts_at__lt=horizon)
        .order_by("starts_at", "-is_primary")
    )
    past = list(
        SupportOnCallShift.objects.select_related("user")
        .filter(ends_at__lte=now)
        .order_by("-ends_at")[:25]
    )
    candidates = list(
        User.objects.filter(is_staff=True).order_by("first_name", "last_name", "email")[:200]
    )

    return render(
        request,
        "schools/super_support_on_call.html",
        {
            "active_primary": get_active_on_call_user(),
            "active_backups": get_active_backup_users(),
            "upcoming": upcoming,
            "past": past,
            "candidates": candidates,
            "now_iso": now.strftime("%Y-%m-%dT%H:%M"),
            "default_end_iso": (now + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M"),
        },
    )


@require_platform_scope(PLATFORM_SCOPE_TEAM_MANAGE)
@require_http_methods(["POST"])
def support_on_call_save(request):
    """Create / update / delete a SupportOnCallShift row."""
    from apps.accounts.models import User
    from apps.siteconfig.models_feature_controls import SupportOnCallShift

    action = (request.POST.get("action") or "create").strip().lower()
    shift_id = (request.POST.get("shift_id") or "").strip()

    if action == "delete" and shift_id:
        SupportOnCallShift.objects.filter(pk=shift_id).delete()
        messages.success(request, "Shift removed.")
        return redirect("super:support_on_call_dashboard")

    user_id = (request.POST.get("user_id") or "").strip()
    role_tag = (request.POST.get("role_tag") or "").strip()[:40]
    is_primary = request.POST.get("is_primary") in ("1", "true", "on", "yes")
    starts_raw = request.POST.get("starts_at") or ""
    ends_raw = request.POST.get("ends_at") or ""
    notes = (request.POST.get("notes") or "").strip()[:240]  # magic-number-allow: string-truncation-cap

    starts_at = _parse_dt(starts_raw)
    ends_at = _parse_dt(ends_raw)
    if not user_id or not starts_at or not ends_at:
        messages.error(request, "User and start/end times are required.")
        return redirect("super:support_on_call_dashboard")
    if ends_at <= starts_at:
        messages.error(request, "End time must be after start time.")
        return redirect("super:support_on_call_dashboard")

    user = User.objects.filter(pk=user_id).first()
    if user is None:
        messages.error(request, "User not found.")
        return redirect("super:support_on_call_dashboard")

    if shift_id:
        shift = SupportOnCallShift.objects.filter(pk=shift_id).first()
        if shift is None:
            messages.error(request, "Shift not found.")
            return redirect("super:support_on_call_dashboard")
        shift.user = user
        shift.role_tag = role_tag
        shift.is_primary = is_primary
        shift.starts_at = starts_at
        shift.ends_at = ends_at
        shift.notes = notes
        shift.save()
        messages.success(request, "Shift updated.")
    else:
        SupportOnCallShift.objects.create(
            user=user,
            role_tag=role_tag,
            is_primary=is_primary,
            starts_at=starts_at,
            ends_at=ends_at,
            notes=notes,
        )
        messages.success(request, "Shift created.")
    return redirect("super:support_on_call_dashboard")


@require_platform_scope(PLATFORM_SCOPE_TEAM_MANAGE)
@require_http_methods(["POST"])
def support_on_call_generate(request):
    """v4.00.45 — Generate N weeks of recurring shifts across a roster.

    Accepts: user_ids[] (2+ users alternate), weeks (1-26), pattern fields
    (days[], start_hour, end_hour, tz_name, role_tag). Calls the SOT helper.
    """
    from apps.siteconfig.support_on_call_generator import generate_recurring_shifts

    raw_user_ids = request.POST.getlist("user_ids")
    try:
        user_ids = [int(v) for v in raw_user_ids if v]
    except (TypeError, ValueError):
        user_ids = []
    if not user_ids:
        messages.error(request, "Select at least one user for the rotation.")
        return redirect("super:support_on_call_dashboard")

    try:
        weeks = int(request.POST.get("weeks") or 4)
    except (TypeError, ValueError):
        weeks = 4
    days = request.POST.getlist("days") or ["mon", "tue", "wed", "thu", "fri"]
    try:
        start_hour = int(request.POST.get("start_hour") or 9)
        end_hour = int(request.POST.get("end_hour") or 17)
    except (TypeError, ValueError):
        start_hour, end_hour = 9, 17
    tz_name = (request.POST.get("tz_name") or "UTC").strip()[:40]
    role_tag = (request.POST.get("role_tag") or "").strip()[:40]
    # v4.00.49 — skip-week support
    skip_weeks_raw = (request.POST.get("skip_weeks") or "").strip()[:120]
    skip_pattern = (request.POST.get("skip_pattern") or "").strip()[:40]

    created = generate_recurring_shifts(
        user_ids,
        {
            "days": days,
            "start_hour": start_hour,
            "end_hour": end_hour,
            "tz_name": tz_name,
            "role_tag": role_tag,
            "skip_weeks": skip_weeks_raw,
            "skip_pattern": skip_pattern,
        },
        weeks=weeks,
    )
    if created:
        messages.success(request, f"Generated {created} shift rows.")
    else:
        messages.warning(request, "No shifts were generated — check the pattern.")
    return redirect("super:support_on_call_dashboard")
