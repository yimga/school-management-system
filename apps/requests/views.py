import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from services.post_delete_navigation import safe_next_url as _safe_next_url

from apps.accounts.models import User
from apps.accounts.utils import get_user_role
from apps.schools.models import SchoolMembership

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
    # tenant-isolation-allow: conditionally scoped by school on next line (reviewed 2026-05-14)
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
        scoped_base.values("status").order_by("status").annotate(count=Count("id"))
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
            "datasets": [
                {
                    "data": [o["count"] for o in status_with_data],
                    "backgroundColor": [
                        colors[i % len(colors)] for i in range(len(status_with_data))
                    ],
                }
            ],
        },
    }

    per_page = _safe_int(
        request.GET.get("page_size", 25), default=25, minimum=10, maximum=100
    )
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

    total_open = status_counts_dict.get(
        AccessRequest.Status.PENDING, 0
    ) + status_counts_dict.get(AccessRequest.Status.CLARIFICATION_REQUESTED, 0)
    phase7_de = {
        "eyebrow": "Approvals home",
        "headline_label": "Open requests",
        "headline_value": total_open,
        "headline_meta": f"{paginator.count} total in scope",
        "metrics": [
            {
                "label": "Pending",
                "value": status_counts_dict.get(AccessRequest.Status.PENDING, 0),
                "meta": "Awaiting action",
                "status": "warn",
            },
            {
                "label": "Approved",
                "value": status_counts_dict.get(AccessRequest.Status.APPROVED, 0),
                "meta": "All time",
                "status": "ok",
            },
            {
                "label": "Denied",
                "value": status_counts_dict.get(AccessRequest.Status.DENIED, 0),
                "meta": "Closed",
                "status": "ok",
            },
        ],
        "urgent_queue": [
            {
                "title": f"{total_open} item(s) need a decision",
                "url": reverse("requests:dashboard") + "?status=PENDING",
                "hint": "Filter to pending and clarification.",
            }
        ]
        if total_open
        else [
            {
                "title": "Inbox clear",
                "url": "",
                "hint": "No pending or in-review items.",
            }
        ],
        "next_actions": [
            {"label": "Filter pending", "url": reverse("requests:dashboard") + "?status=PENDING"},
            {"label": "All requests", "url": reverse("requests:dashboard")},
            {"label": "Backend home", "url": reverse("accounts:backend_dashboard")},
        ],
        "activity": [
            {
                "title": "Latest in table",
                "meta": f"Page {page_obj.number} of {paginator.num_pages}",
            }
        ],
    }

    return render(
        request,
        "requests/dashboard.html",
        {
            "requests": page_obj.object_list,
            "page_obj": page_obj,
            "type_filter": request_type,
            "status_filter": status,
            "search": search,
            "type_options": type_options,
            "status_options": status_options,
            "chart_status_donut_json": json.dumps(chart_status_donut),
            "pagination_extra_query": pagination_extra_query,
            "phase7_de": phase7_de,
        },
    )


@login_required
@user_passes_test(_can_manage_requests)
def request_detail(request: HttpRequest, request_id):
    school = _request_school(request)
    qs = AccessRequest.objects.select_related("requester")
    if school is not None:
        qs = qs.filter(school=school)
    access_request = get_object_or_404(qs, id=request_id)
    if school is not None and access_request.school_id != school.id:
        return HttpResponseForbidden(
            "This request does not belong to the active school."
        )
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

    return render(
        request,
        "requests/detail.html",
        {
            "req": access_request,
            "audits": access_request.audits.select_related("actor")[:50],
            "decisions": access_request.decisions.select_related("decided_by")[:20],
        },
    )


@login_required
def request_module_access(request: HttpRequest):
    if request.method != "POST":
        return redirect("requests:dashboard")

    module = (request.POST.get("module") or "").strip().lower()
    action = (request.POST.get("action") or "read").strip().lower()
    next_url = _safe_next_url(
        request, request.POST.get("next"), reverse("requests:dashboard")
    )

    if action not in {"read", "write"}:
        action = "read"

    title = f"Module access request: {module}" if module else "Module access request"
    summary = (
        f"Requested {action} access for {module}."
        if module
        else "Requested module access."
    )
    details = {"module": module, "action": action}

    create_access_request(
        request_type=AccessRequest.RequestType.MODULE_ACCESS,
        requester=request.user,
        title=title,
        summary=summary,
        details=details,
        school=_request_school(request),
    )

    messages.success(
        request, "Access request submitted. You will be notified when it is reviewed."
    )
    return redirect(next_url)


# Approving six access requests used to cost six page loads and six posts, one
# detail page at a time. That is the "fewer clicks" complaint in its purest form:
# the work is identical for every row, and the platform made the reader repeat it.
#
# Deliberately JavaScript-free. Checkboxes plus two submit buttons is enough, it
# survives an offline box with a flaky bundle, and it keeps the surface clear of
# the inline-handler rule the CSP seal enforces. A select-all convenience is not
# worth a script tag here.
_BULK_DECISION_CAP = 100  # magic-number-allow: one screenful of requests per post


@login_required
@user_passes_test(_can_manage_requests)
def bulk_decide(request: HttpRequest):
    """Apply one decision to every selected access request, atomically."""
    if request.method != "POST":
        return redirect("requests:dashboard")

    back = _safe_next_url(
        request, request.POST.get("next"), reverse("requests:dashboard")
    )
    action = (request.POST.get("action") or "").upper()
    if action not in {
        RequestDecision.Decision.APPROVED,
        RequestDecision.Decision.DENIED,
        RequestDecision.Decision.CLARIFY,
    }:
        messages.error(request, "Unknown action.")
        return redirect(back)

    raw_ids = request.POST.getlist("request_ids")
    if not raw_ids:
        messages.info(request, "Select at least one request first.")
        return redirect(back)
    if len(raw_ids) > _BULK_DECISION_CAP:
        messages.error(
            request,
            f"Select at most {_BULK_DECISION_CAP} requests at once.",
        )
        return redirect(back)

    # Scope BEFORE touching anything: ids arrive from the client, so the queryset
    # is the only thing keeping one school from deciding another's requests.
    #
    # This endpoint FAILS CLOSED where the read paths fail open. `requests_dashboard`
    # deliberately lists unscoped when no school resolves (a reviewed decision, marked
    # in place), which is defensible for a read — but the same shape on a batch WRITE
    # means one post settles every school's requests at once. A test caught exactly
    # that, because `request.school` is set by middleware and is absent on other
    # entry points.
    school = _request_school(request)
    if school is None:
        # Fall back to the acting user's own membership rather than to "everything".
        membership = (
            # tenant-isolation-allow: the request carries no school, so this falls back to the acting user's own membership rather than to everything (both tenancy modes, reviewed 2026-09-01)
            SchoolMembership.objects.filter(user=request.user)
            .select_related("school")
            .order_by("-is_primary")
            .first()
        )
        school = membership.school if membership else None
    if school is None:
        messages.error(
            request,
            "No active school for this session — open a school workspace, or decide "
            "requests individually.",
        )
        return redirect(back)

    qs = AccessRequest.objects.filter(id__in=raw_ids, school=school)
    # Only pending rows are actionable; re-posting a stale page must not silently
    # overturn a decision someone else already made.
    targets = list(qs.filter(status=AccessRequest.Status.PENDING))

    if not targets:
        messages.info(request, "Nothing to do — those requests are no longer pending.")
        return redirect(back)

    reason = (request.POST.get("reason") or "").strip()
    from django.db import transaction

    with transaction.atomic():
        for access_request in targets:
            apply_request_decision(
                request=access_request,
                decision=action,
                reason=reason,
                actor=request.user,
            )

    skipped = len(raw_ids) - len(targets)
    label = {
        RequestDecision.Decision.APPROVED: "approved",
        RequestDecision.Decision.DENIED: "denied",
        RequestDecision.Decision.CLARIFY: "sent back for clarification",
    }[action]
    note = f"{len(targets)} request(s) {label}."
    if skipped > 0:
        note += f" {skipped} skipped — no longer pending or not yours."
    messages.success(request, note)
    return redirect(back)
