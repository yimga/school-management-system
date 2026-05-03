"""DLQ queries and operator remediation for domain + platform webhook deliveries."""

from __future__ import annotations

from django.db.models import F, Q
from django.utils import timezone

from apps.events.models import EventSystemRemediationAudit, WebhookDelivery
from apps.events.tasks import process_webhook_deliveries_batch
from apps.platform_runtime.models import EventWebhookDelivery

def domain_dead_letter_filter():
    return Q(
        status=WebhookDelivery.Status.FAILED,
        retry_count__gte=F("max_attempts"),
    )


def domain_dlq_queryset_for_school(school_pk, *, event_type: str | None = None):
    qs = (
        WebhookDelivery.objects.filter(domain_event__school_id=school_pk)
        .filter(domain_dead_letter_filter())
        .filter(operator_resolution__isnull=True)
        .select_related("subscription", "domain_event")
        .order_by("-created_at")
    )
    if event_type:
        qs = qs.filter(domain_event__event_type=event_type)
    return qs


def platform_dlq_queryset_for_school(
    school_id_str: str, *, event_type: str | None = None
):
    qs = (
        EventWebhookDelivery.objects.filter(
            subscription__school_id=school_id_str,
            status=EventWebhookDelivery.Status.DEAD_LETTER,
            operator_resolution__isnull=True,
        )
        .select_related("subscription", "platform_event")
        .order_by("-created_at")
    )
    if event_type:
        qs = qs.filter(platform_event__event_type=event_type)
    return qs


def _audit(
    school_pk,
    source: str,
    delivery_pk: int,
    action: str,
    actor,
    *,
    reason: str = "",
):
    EventSystemRemediationAudit.objects.create(
        school_id=school_pk,
        delivery_source=source,
        delivery_pk=delivery_pk,
        action=action,
        actor=actor,
        reason=reason or "",
    )


def retry_domain_delivery(delivery: WebhookDelivery, actor, *, flush_attempts: int = 5):
    sid = delivery.domain_event.school_id
    now = timezone.now()
    delivery.status = WebhookDelivery.Status.PENDING
    delivery.retry_count = 0
    delivery.scheduled_for = now
    delivery.operator_resolution = None
    delivery.operator_resolution_reason = ""
    delivery.operator_resolution_by = None
    delivery.operator_resolution_at = None
    delivery.save(
        update_fields=[
            "status",
            "retry_count",
            "scheduled_for",
            "operator_resolution",
            "operator_resolution_reason",
            "operator_resolution_by",
            "operator_resolution_at",
        ]
    )
    _audit(
        sid,
        EventSystemRemediationAudit.DeliverySource.DOMAIN_WEBHOOK,
        delivery.pk,
        EventSystemRemediationAudit.Action.RETRY,
        actor,
        reason="operator_retry",
    )
    process_webhook_deliveries_batch(batch_size=max(1, int(flush_attempts)))


def retry_platform_delivery(delivery: EventWebhookDelivery, actor):
    from apps.platform_runtime.tasks import deliver_event_webhook_task

    ev = delivery.platform_event
    sid_raw = getattr(ev, "school_id", None) or delivery.subscription.school_id
    try:
        from uuid import UUID

        school_uuid = UUID(str(sid_raw).strip())
    except ValueError:
        school_uuid = None
    now = timezone.now()
    delivery.status = EventWebhookDelivery.Status.PENDING
    delivery.attempt_count = 0
    delivery.next_retry_at = now
    delivery.last_error = ""
    delivery.operator_resolution = None
    delivery.operator_resolution_reason = ""
    delivery.operator_resolution_by = None
    delivery.operator_resolution_at = None
    delivery.save(
        update_fields=[
            "status",
            "attempt_count",
            "next_retry_at",
            "last_error",
            "operator_resolution",
            "operator_resolution_reason",
            "operator_resolution_by",
            "operator_resolution_at",
            "updated_at",
        ]
    )
    _audit(
        school_uuid,
        EventSystemRemediationAudit.DeliverySource.PLATFORM_WEBHOOK,
        delivery.pk,
        EventSystemRemediationAudit.Action.RETRY,
        actor,
        reason="operator_retry",
    )
    deliver_event_webhook_task.delay(delivery.pk)


def resolve_domain_delivery(delivery: WebhookDelivery, actor, *, reason: str):
    sid = delivery.domain_event.school_id
    now = timezone.now()
    delivery.operator_resolution = "resolved"
    delivery.operator_resolution_reason = reason[:4000]
    delivery.operator_resolution_by = actor
    delivery.operator_resolution_at = now
    delivery.save(
        update_fields=[
            "operator_resolution",
            "operator_resolution_reason",
            "operator_resolution_by",
            "operator_resolution_at",
        ]
    )
    _audit(
        sid,
        EventSystemRemediationAudit.DeliverySource.DOMAIN_WEBHOOK,
        delivery.pk,
        EventSystemRemediationAudit.Action.RESOLVED,
        actor,
        reason=reason,
    )


def ignore_domain_delivery(delivery: WebhookDelivery, actor, *, reason: str):
    sid = delivery.domain_event.school_id
    now = timezone.now()
    delivery.operator_resolution = "ignored"
    delivery.operator_resolution_reason = reason[:4000]
    delivery.operator_resolution_by = actor
    delivery.operator_resolution_at = now
    delivery.save(
        update_fields=[
            "operator_resolution",
            "operator_resolution_reason",
            "operator_resolution_by",
            "operator_resolution_at",
        ]
    )
    _audit(
        sid,
        EventSystemRemediationAudit.DeliverySource.DOMAIN_WEBHOOK,
        delivery.pk,
        EventSystemRemediationAudit.Action.IGNORED,
        actor,
        reason=reason,
    )


def resolve_platform_delivery(delivery: EventWebhookDelivery, actor, *, reason: str):
    ev = delivery.platform_event
    sid_raw = getattr(ev, "school_id", None) or delivery.subscription.school_id
    from uuid import UUID

    school_uuid = UUID(str(sid_raw).strip())
    now = timezone.now()
    delivery.operator_resolution = "resolved"
    delivery.operator_resolution_reason = reason[:4000]
    delivery.operator_resolution_by = actor
    delivery.operator_resolution_at = now
    delivery.save(
        update_fields=[
            "operator_resolution",
            "operator_resolution_reason",
            "operator_resolution_by",
            "operator_resolution_at",
            "updated_at",
        ]
    )
    _audit(
        school_uuid,
        EventSystemRemediationAudit.DeliverySource.PLATFORM_WEBHOOK,
        delivery.pk,
        EventSystemRemediationAudit.Action.RESOLVED,
        actor,
        reason=reason,
    )


def ignore_platform_delivery(delivery: EventWebhookDelivery, actor, *, reason: str):
    ev = delivery.platform_event
    sid_raw = getattr(ev, "school_id", None) or delivery.subscription.school_id
    from uuid import UUID

    school_uuid = UUID(str(sid_raw).strip())
    now = timezone.now()
    delivery.operator_resolution = "ignored"
    delivery.operator_resolution_reason = reason[:4000]
    delivery.operator_resolution_by = actor
    delivery.operator_resolution_at = now
    delivery.save(
        update_fields=[
            "operator_resolution",
            "operator_resolution_reason",
            "operator_resolution_by",
            "operator_resolution_at",
            "updated_at",
        ]
    )
    _audit(
        school_uuid,
        EventSystemRemediationAudit.DeliverySource.PLATFORM_WEBHOOK,
        delivery.pk,
        EventSystemRemediationAudit.Action.IGNORED,
        actor,
        reason=reason,
    )
