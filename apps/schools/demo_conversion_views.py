"""
Forced conversion demo step machine (attendance → marks → report → create-school CTA).

Session key ``rmc_demo_flow_step`` holds the furthest completed stage so users cannot skip ahead.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

_SESSION_STEP = "rmc_demo_flow_step"
_STEP_ORDER = ("attendance", "marks", "report", "complete")


def _step_index(name: str) -> int:
    try:
        return _STEP_ORDER.index(name)
    except ValueError:
        return -1


def _session_step(request) -> str:
    raw = request.session.get(_SESSION_STEP)
    if raw not in _STEP_ORDER:
        request.session[_SESSION_STEP] = "attendance"
        request.session.modified = True
        return "attendance"
    return raw


def _emit_demo_funnel(request, school, event_type: str, **meta) -> None:
    try:
        from apps.schools.funnel_events import record_marketing_funnel_event

        record_marketing_funnel_event(
            event_type, request, school=school, user=request.user, metadata=meta
        )
    except Exception:
        pass


@login_required
@require_http_methods(["GET"])
def demo_flow_index(request: HttpRequest):
    return HttpResponseRedirect(reverse("demo_flow_attendance"))


@login_required
@require_http_methods(["GET"])
def demo_flow_attendance(request: HttpRequest):
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseRedirect(reverse("home"))
    step = _session_step(request)
    req_idx = _step_index("attendance")
    cur_idx = _step_index(step)
    if cur_idx < req_idx:
        return HttpResponseRedirect(reverse("demo_flow_attendance"))
    if cur_idx > req_idx:
        return HttpResponseRedirect(reverse("demo_flow_marks"))
    if not request.session.get("rmc_demo_started_logged"):
        try:
            from apps.schools.funnel_events import record_school_funnel_once

            record_school_funnel_once(
                "onboarding_start",
                school,
                request,
                user=request.user,
                metadata={"source": "demo_conversion_flow", "step": "attendance"},
            )
            _emit_demo_funnel(request, school, "demo_started", source="demo_conversion_flow")
        except Exception:
            pass
        request.session["rmc_demo_started_logged"] = True
        request.session.modified = True
    ctx = {
        "demo_step": "attendance",
        "demo_next_url": reverse("demo_flow_marks"),
        "school_name": getattr(school, "name", "") or "",
    }
    return render(request, "schools/demo_flow_attendance.html", ctx)


@login_required
@require_http_methods(["POST"])
def demo_flow_attendance_complete(request: HttpRequest):
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseRedirect(reverse("home"))
    request.session[_SESSION_STEP] = "marks"
    request.session.modified = True
    try:
        from apps.schools.funnel_events import record_school_funnel_once

        record_school_funnel_once(
            "demo_attendance_completed",
            school,
            request,
            user=request.user,
            metadata={"source": "demo_flow_attendance"},
        )
    except Exception:
        pass
    return HttpResponseRedirect(reverse("demo_flow_marks"))


@login_required
@require_http_methods(["GET"])
def demo_flow_marks(request: HttpRequest):
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseRedirect(reverse("home"))
    step = _session_step(request)
    if _step_index(step) < _step_index("marks"):
        return HttpResponseRedirect(reverse("demo_flow_attendance"))
    ctx = {
        "demo_step": "marks",
        "demo_prev_url": reverse("demo_flow_attendance"),
        "demo_next_url": reverse("demo_flow_report"),
        "school_name": getattr(school, "name", "") or "",
    }
    return render(request, "schools/demo_flow_marks.html", ctx)


@login_required
@require_http_methods(["POST"])
def demo_flow_marks_complete(request: HttpRequest):
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseRedirect(reverse("home"))
    if _step_index(_session_step(request)) < _step_index("marks"):
        return HttpResponseRedirect(reverse("demo_flow_attendance"))
    request.session[_SESSION_STEP] = "report"
    request.session.modified = True
    try:
        from apps.schools.funnel_events import record_school_funnel_once

        record_school_funnel_once(
            "demo_marks_completed",
            school,
            request,
            user=request.user,
            metadata={"source": "demo_flow_marks"},
        )
    except ImportError:
        pass
    return HttpResponseRedirect(reverse("demo_flow_report"))


@login_required
@require_http_methods(["GET"])
def demo_flow_report(request: HttpRequest):
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseRedirect(reverse("home"))
    step = _session_step(request)
    if _step_index(step) < _step_index("report"):
        if _step_index(step) < _step_index("marks"):
            return HttpResponseRedirect(reverse("demo_flow_attendance"))
        return HttpResponseRedirect(reverse("demo_flow_marks"))
    ctx = {
        "demo_step": "report",
        "demo_prev_url": reverse("demo_flow_marks"),
        "demo_next_url": reverse("demo_flow_complete"),
        "school_name": getattr(school, "name", "") or "",
    }
    return render(request, "schools/demo_flow_report.html", ctx)


@login_required
@require_http_methods(["POST"])
def demo_flow_report_complete(request: HttpRequest):
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseRedirect(reverse("home"))
    st = _session_step(request)
    if _step_index(st) < _step_index("report"):
        if _step_index(st) < _step_index("marks"):
            return HttpResponseRedirect(reverse("demo_flow_attendance"))
        return HttpResponseRedirect(reverse("demo_flow_marks"))
    request.session[_SESSION_STEP] = "complete"
    request.session.modified = True
    try:
        from apps.schools.funnel_events import record_school_funnel_once

        record_school_funnel_once(
            "demo_report_completed",
            school,
            request,
            user=request.user,
            metadata={"source": "demo_flow_report"},
        )
        record_school_funnel_once(
            "first_result",
            school,
            request,
            user=request.user,
            metadata={"source": "demo_flow_report"},
        )
    except Exception:
        pass
    return HttpResponseRedirect(reverse("demo_flow_complete"))


@login_required
@require_http_methods(["GET"])
def demo_flow_complete(request: HttpRequest):
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseRedirect(reverse("home"))
    step = _session_step(request)
    if step != "complete":
        if step == "attendance":
            return HttpResponseRedirect(reverse("demo_flow_attendance"))
        if step == "marks":
            return HttpResponseRedirect(reverse("demo_flow_marks"))
        if step == "report":
            return HttpResponseRedirect(reverse("demo_flow_report"))
        return HttpResponseRedirect(reverse("demo_flow_attendance"))
    signup_url = "/signup/"
    try:
        from apps.schools.host_routing import get_canonical_base_domain

        scheme = getattr(request, "scheme", "https") or "https"
        host = get_canonical_base_domain()
        signup_url = f"{scheme}://{host}/signup/"
    except Exception:
        pass
    try:
        from apps.schools.funnel_events import record_school_funnel_once

        record_school_funnel_once(
            "demo_cta_seen",
            school,
            request,
            user=request.user,
            metadata={"source": "demo_conversion_flow", "step": "complete"},
        )
        record_school_funnel_once(
            "onboarding_complete",
            school,
            request,
            user=request.user,
            metadata={"source": "demo_conversion_flow", "step": "complete"},
        )
    except Exception:
        pass
    ctx = {
        "demo_step": "complete",
        "create_school_url": signup_url,
        "school_name": getattr(school, "name", "") or "",
    }
    return render(request, "schools/demo_flow_complete.html", ctx)
