"""Tenant-safe operator console: domain outbox + platform event log + replay."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from apps.events.event_contract import domain_event_to_contract, payload_summary
from apps.events.models import DomainEvent, WebhookDelivery
from apps.events.replay_ops import clone_domain_event_for_operator_replay
from apps.events.tasks import process_outbox_batch
from apps.platform_runtime.event_contract import platform_event_to_contract
from apps.platform_runtime.event_bus import replay_event
from apps.platform_runtime.models import EventWebhookDelivery, PlatformEventLog


def _require_staff_school(request):
    if not request.user.is_authenticated:
        return False
    if not getattr(request.user, "is_staff", False):
        return False
    return getattr(request, "school", None) is not None


def _school_pk_str(request):
    sch = getattr(request, "school", None)
    return str(sch.pk) if sch is not None else ""


@never_cache
@login_required
@require_http_methods(["GET"])
def event_console(request):
    if not _require_staff_school(request):
        return HttpResponseForbidden("Staff on a school tenant host is required.")
    school = request.school
    sid = school.pk

    domain_events = list(
        DomainEvent.objects.filter(school_id=sid).order_by("-created_at")[:80]
    )
    platform_events = list(
        PlatformEventLog.objects.filter(school_id=str(sid)).order_by("-pk")[:80]
    )

    domain_rows = []
    for ev in domain_events:
        contract = domain_event_to_contract(ev)
        domain_rows.append(
            {
                "contract": contract,
                "summary": payload_summary(contract.get("payload")),
                "detail_url": reverse(
                    "events:event_domain_detail", kwargs={"event_id": ev.id}
                ),
            }
        )

    platform_rows = []
    for row in platform_events:
        contract = platform_event_to_contract(row)
        platform_rows.append(
            {
                "contract": contract,
                "summary": payload_summary(contract.get("payload")),
                "detail_url": reverse(
                    "events:event_platform_detail", kwargs={"event_pk": row.pk}
                ),
            }
        )

    return render(
        request,
        "events/event_console.html",
        {
            "page_title": "Event Timeline",
            "page_subtitle": (
                "Domain outbox (integrations) and platform event log (workflows / bus) "
                "for this tenant. Replays are audited; duplicates use new IDs / idempotency keys."
            ),
            "domain_rows": domain_rows,
            "platform_rows": platform_rows,
            "action_url": reverse("accounts:backend_dashboard"),
            "dlq_url": reverse("events:event_dlq_console"),
            "analytics_url": reverse("events:event_analytics_console"),
        },
    )


@never_cache
@login_required
@require_http_methods(["GET"])
def event_domain_detail(request, event_id):
    if not _require_staff_school(request):
        return HttpResponseForbidden("Staff on a school tenant host is required.")
    ev = DomainEvent.objects.filter(
        pk=event_id, school_id=request.school.pk
    ).first()
    if ev is None:
        raise Http404("Domain event not found for this tenant.")
    deliveries = list(
        WebhookDelivery.objects.filter(domain_event=ev)  # tenant-isolation-allow: platform-operator-webhook-delivery-console
        .select_related("subscription")
        .order_by("-created_at")[:40]
    )
    contract = domain_event_to_contract(ev)
    replay_eligible = True
    replay_note = ""
    if ev.status == DomainEvent.Status.PENDING:
        replay_note = "Event is still pending; replay clones a processed row after outbox drains."

    matching_visual_workflows = []
    try:
        from apps.automation.workflow_graph_models import Workflow

        matching_visual_workflows = list(
            Workflow.objects.filter(
                school=request.school, trigger_event=ev.event_type
            ).order_by("-updated_at")[:8]
        )
    except Exception:
        matching_visual_workflows = []
    outcomes_console_url = ""
    try:
        outcomes_console_url = reverse("automation:outcomes_console")
    except Exception:
        outcomes_console_url = ""

    return render(
        request,
        "events/event_domain_detail.html",
        {
            "event": ev,
            "contract": contract,
            "contract_json": json.dumps(contract, indent=2, sort_keys=True, default=str),
            "payload_summary": payload_summary(contract.get("payload"), max_keys=40),
            "deliveries": deliveries,
            "replay_eligible": replay_eligible,
            "replay_note": replay_note,
            "console_url": reverse("events:event_console"),
            "matching_visual_workflows": matching_visual_workflows,
            "outcomes_console_url": outcomes_console_url,
            "page_title": f"Domain event {ev.id}",
        },
    )


@never_cache
@login_required
@require_http_methods(["GET"])
def event_platform_detail(request, event_pk: int):
    if not _require_staff_school(request):
        return HttpResponseForbidden("Staff on a school tenant host is required.")
    row = PlatformEventLog.objects.filter(
        pk=event_pk, school_id=_school_pk_str(request)
    ).first()
    if row is None:
        raise Http404("Platform event not found for this tenant.")
    deliveries = list(
        EventWebhookDelivery.objects.filter(platform_event=row)
        .select_related("subscription")
        .order_by("-pk")[:40]
    )
    contract = platform_event_to_contract(row)
    replay_eligible = row.event_type != "platform_event_replayed"

    matching_visual_workflows = []
    try:
        from apps.automation.workflow_graph_models import Workflow

        matching_visual_workflows = list(
            Workflow.objects.filter(
                school=request.school, trigger_event=row.event_type
            ).order_by("-updated_at")[:8]
        )
    except Exception:
        matching_visual_workflows = []
    outcomes_console_url = ""
    try:
        outcomes_console_url = reverse("automation:outcomes_console")
    except Exception:
        outcomes_console_url = ""

    return render(
        request,
        "events/event_platform_detail.html",
        {
            "row": row,
            "contract": contract,
            "contract_json": json.dumps(contract, indent=2, sort_keys=True, default=str),
            "payload_summary": payload_summary(contract.get("payload"), max_keys=40),
            "deliveries": deliveries,
            "replay_eligible": replay_eligible,
            "console_url": reverse("events:event_console"),
            "matching_visual_workflows": matching_visual_workflows,
            "outcomes_console_url": outcomes_console_url,
            "page_title": f"Platform event {row.pk}",
        },
    )


@never_cache
@login_required
@require_POST
def event_replay(request):
    if not _require_staff_school(request):
        return HttpResponseForbidden("Staff on a school tenant host is required.")
    source = (request.POST.get("source") or "").strip().lower()
    dispatch_webhooks = (request.POST.get("dispatch_webhooks") or "").strip() in (
        "1",
        "true",
        "yes",
        "on",
    )
    process_outbox = (request.POST.get("process_outbox") or "1").strip() in (
        "1",
        "true",
        "yes",
        "on",
        "",
    )

    if source == "domain":
        raw_id = (request.POST.get("domain_event_id") or "").strip()
        ev = DomainEvent.objects.filter(
            pk=raw_id, school_id=request.school.pk
        ).first()
        if ev is None:
            raise Http404("Domain event not found for this tenant.")
        dup = clone_domain_event_for_operator_replay(ev, actor=request.user)
        processed = 0
        if process_outbox:
            processed = process_outbox_batch(batch_size=50)
        messages.success(
            request,
            f"Replay queued: new domain event {dup.id} (outbox rows processed: {processed}).",
        )
        return redirect("events:event_domain_detail", event_id=dup.id)

    if source == "platform":
        try:
            pk = int(request.POST.get("platform_event_pk") or "0")
        except ValueError:
            pk = 0
        row = PlatformEventLog.objects.filter(
            pk=pk, school_id=_school_pk_str(request)
        ).first()
        if row is None:
            raise Http404("Platform event not found for this tenant.")
        result = replay_event(pk, dispatch_webhooks=dispatch_webhooks)
        if not result.get("ok"):
            messages.error(request, f"Replay failed: {result.get('error')}")
            return redirect("events:event_platform_detail", event_pk=pk)
        messages.success(
            request,
            "Replay invoked for platform event "
            f"{pk} (webhooks={'on' if dispatch_webhooks else 'off'}). "
            "Audit row platform_event_replayed may appear when applicable.",
        )
        return redirect("events:event_platform_detail", event_pk=pk)

    messages.error(request, "Unknown replay source.")
    return redirect("events:event_console")
