from __future__ import annotations

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.billing.models import (
    BillingAccount,
    BillingProcessorSyncEvent,
    PlatformBillingProcessorConfig,
)
from apps.billing.processors import get_platform_billing_processor
from apps.billing.services import apply_processor_snapshot, finalize_marketplace_addon_payment, sync_stripe_connect_from_webhook_snapshot
from apps.observability.incident_services import upsert_platform_incident
from apps.observability.models import PlatformIncident
from apps.schools.models import School

_WEBHOOK_SOURCE = "billing.processor_webhook"
_JSON_CONTENT_TYPES = {"application/json"}


def _record_failed_event(
    *, processor_code: str, event_type: str, payload: dict, message: str
):
    return BillingProcessorSyncEvent.objects.create(
        processor_code=processor_code,
        event_type=event_type,
        status=BillingProcessorSyncEvent.Status.FAILED,
        payload=payload or {},
        message=message,
        happened_at=timezone.now(),
    )


def _resolve_school(snapshot: dict):
    school = None
    if snapshot.get("school_id"):
        school = School.objects.filter(pk=snapshot["school_id"], is_active=True).first()
    if school is None and snapshot.get("school_slug"):
        slug = str(snapshot["school_slug"]).strip()
        school = School.objects.filter(slug=slug, is_active=True).first()
        if school is None:
            school = School.objects.filter(subdomain=slug, is_active=True).first()
    if school is None and snapshot.get("external_customer_ref"):
        account = (
            BillingAccount.objects.select_related("school")
            .filter(
                external_customer_ref=str(snapshot["external_customer_ref"]).strip()
            )
            .first()
        )
        if account is not None:
            school = account.school
    return school


def _upsert_webhook_incident(
    *,
    incident_key: str,
    processor_code: str,
    title: str,
    summary: str,
    severity: str,
    details: dict,
):
    upsert_platform_incident(
        incident_key=incident_key,
        title=title,
        incident_type=PlatformIncident.IncidentType.INTEGRATION,
        severity=severity,
        summary=summary,
        source_system=_WEBHOOK_SOURCE,
        details={"processor_code": processor_code, **(details or {})},
    )


def _request_uses_supported_json_content_type(request) -> bool:
    content_type = (
        (request.content_type or request.META.get("CONTENT_TYPE") or "")
        .split(";", 1)[0]
        .strip()
        .lower()
    )
    if not content_type:
        return True
    return content_type in _JSON_CONTENT_TYPES or content_type.endswith("+json")


@csrf_exempt
@require_POST
def platform_billing_processor_webhook(request, processor_code: str):
    processor_code = str(processor_code or "").strip().lower()
    config = PlatformBillingProcessorConfig.objects.filter(
        code=processor_code, is_active=True
    ).first()
    if config is None:
        _upsert_webhook_incident(
            incident_key=f"billing-webhook-config:{processor_code}",
            processor_code=processor_code,
            title=f"Billing webhook rejected: {processor_code}",
            summary="Webhook request targeted an unknown or inactive platform billing processor.",
            severity=PlatformIncident.Severity.HIGH,
            details={"reason": "unknown_processor"},
        )
        return JsonResponse(
            {"status": "error", "error": "Unknown processor."}, status=404
        )
    if not _request_uses_supported_json_content_type(request):
        _record_failed_event(
            processor_code=processor_code,
            event_type="webhook_rejected",
            payload={},
            message="Unsupported Content-Type. Expected JSON webhook payload.",
        )
        _upsert_webhook_incident(
            incident_key=f"billing-webhook-content-type:{processor_code}",
            processor_code=processor_code,
            title=f"Billing webhook rejected: {processor_code}",
            summary="Webhook request used an unsupported Content-Type.",
            severity=PlatformIncident.Severity.HIGH,
            details={"reason": "unsupported_content_type"},
        )
        return JsonResponse(
            {"status": "error", "error": "Content-Type must be application/json."},
            status=415,
        )

    # §2.4 Webhook signature verification; reject missing or invalid signature with 401.
    processor = get_platform_billing_processor(config)
    payload, raw_body = processor.parse_request(request)
    is_valid, error_message = processor.verify_request(request, raw_body)
    if not is_valid:
        _record_failed_event(
            processor_code=processor_code,
            event_type=str(payload.get("type") or "webhook_rejected"),
            payload=payload,
            message=error_message,
        )
        _upsert_webhook_incident(
            incident_key=f"billing-webhook-signature:{processor_code}",
            processor_code=processor_code,
            title=f"Billing webhook rejected: {processor_code}",
            summary=error_message,
            severity=PlatformIncident.Severity.CRITICAL,
            details={"reason": "signature_validation_failed"},
        )
        return JsonResponse({"status": "error", "error": error_message}, status=401)

    config.last_webhook_at = timezone.now()
    config.save(update_fields=["last_webhook_at", "updated_at"])

    raw_event_type = str(
        payload.get("type") or payload.get("event_type") or "processor.webhook"
    )
    if config.event_allowlist and raw_event_type not in set(config.event_allowlist):
        BillingProcessorSyncEvent.objects.create(
            processor_code=processor_code,
            event_type=raw_event_type,
            status=BillingProcessorSyncEvent.Status.IGNORED,
            payload=payload,
            message="Event ignored because it is not on the configured allowlist.",
            happened_at=timezone.now(),
        )
        return JsonResponse(
            {"status": "ignored", "event_type": raw_event_type}, status=202
        )

    normalized_snapshots = processor.normalize(payload)
    if not normalized_snapshots:
        _record_failed_event(
            processor_code=processor_code,
            event_type=raw_event_type,
            payload=payload,
            message="Webhook payload did not produce any billing snapshots.",
        )
        _upsert_webhook_incident(
            incident_key=f"billing-webhook-normalize:{processor_code}",
            processor_code=processor_code,
            title=f"Billing webhook normalization failed: {processor_code}",
            summary="Webhook payload was accepted but did not contain any normalized billing snapshots.",
            severity=PlatformIncident.Severity.HIGH,
            details={"event_type": raw_event_type},
        )
        return JsonResponse(
            {"status": "error", "error": "No billing snapshots were produced."},
            status=400,
        )

    processed = 0
    unresolved = 0
    for snapshot in normalized_snapshots:
        school = _resolve_school(snapshot)
        event_type = (
            str(snapshot.get("event_type") or raw_event_type).strip() or raw_event_type
        )
        if school is None:
            unresolved += 1
            _record_failed_event(
                processor_code=processor_code,
                event_type=event_type,
                payload=snapshot,
                message="Unable to resolve a school from webhook metadata or external customer reference.",
            )
            _upsert_webhook_incident(
                incident_key=f"billing-webhook-school-resolution:{processor_code}:{snapshot.get('external_customer_ref') or event_type}",
                processor_code=processor_code,
                title=f"Billing webhook school resolution failed: {processor_code}",
                summary="Webhook payload could not be mapped to a tenant school.",
                severity=PlatformIncident.Severity.HIGH,
                details={
                    "event_type": event_type,
                    "external_customer_ref": snapshot.get("external_customer_ref"),
                },
            )
            continue

        apply_processor_snapshot(
            school=school,
            processor_code=processor_code,
            event_type=event_type,
            account_status=snapshot.get("account_status"),
            subscription_status=snapshot.get("subscription_status"),
            external_customer_ref=str(
                snapshot.get("external_customer_ref") or ""
            ).strip(),
            external_subscription_ref=str(
                snapshot.get("external_subscription_ref") or ""
            ).strip(),
            currency_code=snapshot.get("currency_code"),
            billed_amount=snapshot.get("billed_amount"),
            current_period_start=snapshot.get("current_period_start"),
            current_period_end=snapshot.get("current_period_end"),
            trial_end_date=snapshot.get("trial_end_date"),
            happened_at=snapshot.get("happened_at") or timezone.now(),
            payload=snapshot.get("payload") or snapshot,
            message=str(snapshot.get("message") or "").strip(),
            processor_source_ref=str(snapshot.get("processor_source_ref") or "").strip(),
        )
        sync_stripe_connect_from_webhook_snapshot(school=school, snapshot=snapshot)
        finalize_marketplace_addon_payment(
            school,
            snapshot,
            processor_code=processor_code,
        )
        processed += 1

    if processed == 0:
        return JsonResponse(
            {"status": "error", "error": "No billing snapshots were applied."},
            status=422,
        )

    return JsonResponse(
        {
            "status": "accepted",
            "processor_code": processor_code,
            "processed": processed,
            "unresolved": unresolved,
        },
        status=202,
    )
