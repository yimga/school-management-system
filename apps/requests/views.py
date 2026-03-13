import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.utils import get_user_role

from .models import AccessRequest, RequestDecision
from .services import apply_request_decision, create_access_request


def _safe_int(raw, *, default, minimum=None, maximum=None):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _safe_next_url(request: HttpRequest, candidate: str | None, fallback: str) -> str:
    if not candidate:
        return fallback
    value = str(candidate).strip()
    if not value:
        return fallback
    if url_has_allowed_host_and_scheme(
        url=value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return fallback


def _request_school(request: HttpRequest):
    return (getattr(request, "__dict__", {}) or {}).get("school")


def _can_manage_requests(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    role = get_user_role(user)
    return role in {
        User.Role.SUPERADMIN,
        User.Role.ADMIN,
        User.Role.IT_ADMIN,
        User.Role.LEADERSHIP,
        User.Role.PRINCIPAL,
        User.Role.VICE_PRINCIPAL,
        User.Role.DEAN,
        User.Role.BURSAR,
        User.Role.FINANCE_STAFF,
        User.Role.ACADEMICS_STAFF,
        User.Role.COMMS_STAFF,
    }


@login_required
@user_passes_test(_can_manage_requests)
def requests_dashboard(request: HttpRequest):
    school = _request_school(request)
    qs = AccessRequest.objects.select_related("requester").order_by("-requested_at")
    scoped_base = AccessRequest.objects.all()
    if school is not None:
        qs = qs.filter(school=school)
        scoped_base = scoped_base.filter(school=school)
    request_type = request.GET.get("type", "all")
    status = request.GET.get("status", "all")
    search = (request.GET.get("q") or "").strip()

    if request_type != "all":
        qs = qs.filter(request_type=request_type)
    if status != "all":
        qs = qs.filter(status=status)
    if search:
        qs = qs.filter(reference__icontains=search)

    type_counts = (
        scoped_base.values("request_type")
        .order_by("request_type")
        .annotate(count=Count("id"))
    )
    status_counts = (
        scoped_base.values("status")
        .order_by("status")
        .annotate(count=Count("id"))
    )

    type_counts_dict = {row["request_type"]: row["count"] for row in type_counts}
    status_counts_dict = {row["status"]: row["count"] for row in status_counts}

    type_options = [
        {"key": key, "label": label, "count": type_counts_dict.get(key, 0)}
        for key, label in AccessRequest.RequestType.choices
    ]
    status_options = [
        {"key": key, "label": label, "count": status_counts_dict.get(key, 0)}
        for key, label in AccessRequest.Status.choices
    ]

    status_with_data = [o for o in status_options if o["count"] > 0]
    colors = ["#ffc107", "#198754", "#dc3545", "#6c757d", "#0d6efd"]
    chart_status_donut = {
        "type": "doughnut",
        "data": {
            "labels": [o["label"] for o in status_with_data],
            "datasets": [{
                "data": [o["count"] for o in status_with_data],
                "backgroundColor": [colors[i % len(colors)] for i in range(len(status_with_data))],
            }],
        },
    }

    per_page = _safe_int(request.GET.get("page_size", 25), default=25, minimum=10, maximum=100)
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)

    q = request.GET.copy()
    q.pop("page", None)
    pagination_extra_query = q.urlencode()

    return render(request, "requests/dashboard.html", {
        "requests": page_obj.object_list,
        "page_obj": page_obj,
        "type_filter": request_type,
        "status_filter": status,
        "search": search,
        "type_options": type_options,
        "status_options": status_options,
        "chart_status_donut_json": json.dumps(chart_status_donut),
        "pagination_extra_query": pagination_extra_query,
    })


@login_required
@user_passes_test(_can_manage_requests)
def request_detail(request: HttpRequest, request_id):
    school = _request_school(request)
    qs = AccessRequest.objects.select_related("requester")
    if school is not None:
        qs = qs.filter(school=school)
    access_request = get_object_or_404(qs, id=request_id)
    if school is not None and access_request.school_id != school.id:
        return HttpResponseForbidden("This request does not belong to the active school.")
    if request.method == "POST":
        action = request.POST.get("action", "").upper()
        reason = (request.POST.get("reason") or "").strip()
        if action not in {
            RequestDecision.Decision.APPROVED,
            RequestDecision.Decision.DENIED,
            RequestDecision.Decision.CLARIFY,
        }:
            messages.error(request, "Unknown action.")
            return redirect("requests:detail", request_id=access_request.id)
        apply_request_decision(
            request=access_request,
            decision=action,
            reason=reason,
            actor=request.user,
        )
        messages.success(request, f"Request {access_request.reference} updated.")
        return redirect("requests:detail", request_id=access_request.id)

    return render(request, "requests/detail.html", {
        "req": access_request,
        "audits": access_request.audits.select_related("actor")[:50],
        "decisions": access_request.decisions.select_related("decided_by")[:20],
    })


@login_required
def request_module_access(request: HttpRequest):
    if request.method != "POST":
        return redirect("requests:dashboard")

    module = (request.POST.get("module") or "").strip().lower()
    action = (request.POST.get("action") or "read").strip().lower()
    next_url = _safe_next_url(request, request.POST.get("next"), reverse("requests:dashboard"))

    if action not in {"read", "write"}:
        action = "read"

    title = f"Module access request: {module}" if module else "Module access request"
    summary = f"Requested {action} access for {module}." if module else "Requested module access."
    details = {"module": module, "action": action}

    create_access_request(
        request_type=AccessRequest.RequestType.MODULE_ACCESS,
        requester=request.user,
        title=title,
        summary=summary,
        details=details,
        school=_request_school(request),
    )

    messages.success(request, "Access request submitted. You will be notified when it is reviewed.")
    return redirect(next_url)
