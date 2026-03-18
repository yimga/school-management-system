"""Compatibility layer between legacy Integration and ServiceIntegration models.

ServiceIntegration is the source of truth for identity/interoperability runtime
paths (OIDC, SCIM, OneRoster, LTI, webhooks). Integration remains supported for
legacy admin/API-center and payment/email style connectors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Q

from apps.siteconfig.models import Integration, ServiceIntegration


@dataclass(frozen=True)
class IntegrationRecord:
    source: str
    service_name: str
    service_type: str
    endpoint_url: str
    is_active: bool
    config: dict[str, Any]
    enabled_scopes: list[str]
    integration_id: int


def map_legacy_provider_to_service_type(legacy: Integration) -> str:
    category = str(getattr(legacy, "category", "") or "").upper()
    provider = str(getattr(legacy, "provider", "") or "").lower()
    if category == "LMS" or provider == "lms":
        return ServiceIntegration.ServiceType.LTI
    if provider == "whatsapp":
        return ServiceIntegration.ServiceType.WHATSAPP
    if provider == "push":
        return ServiceIntegration.ServiceType.PUSH
    if provider == "stripe":
        return ServiceIntegration.ServiceType.STRIPE
    if provider == "badges":
        return ServiceIntegration.ServiceType.BADGES
    if provider in {"email", "sms"}:
        return ServiceIntegration.ServiceType.WEBHOOK
    if provider in {"payments", "analytics"}:
        return ServiceIntegration.ServiceType.OAUTH
    return ServiceIntegration.ServiceType.OTHER


def _legacy_to_record(legacy: Integration) -> IntegrationRecord:
    cfg = dict(legacy.config or {})
    scopes = cfg.get("enabled_scopes") or legacy.allowed_scopes or []
    if isinstance(scopes, dict):
        scopes = [k for k, v in scopes.items() if v]
    if not isinstance(scopes, list):
        scopes = []
    endpoint_url = str(cfg.get("endpoint_url") or cfg.get("base_url") or "").strip()
    return IntegrationRecord(
        source="legacy_integration",
        service_name=(legacy.slug or legacy.name or "").strip(),
        service_type=map_legacy_provider_to_service_type(legacy),
        endpoint_url=endpoint_url,
        is_active=bool(legacy.enabled),
        config=cfg,
        enabled_scopes=[str(x).strip() for x in scopes if str(x).strip()],
        integration_id=legacy.pk,
    )


def _service_to_record(service: ServiceIntegration) -> IntegrationRecord:
    return IntegrationRecord(
        source="service_integration",
        service_name=service.service_name,
        service_type=service.service_type,
        endpoint_url=service.endpoint_url or "",
        is_active=bool(service.is_active),
        config=dict(service.config or {}),
        enabled_scopes=[
            str(x).strip() for x in (service.enabled_scopes or []) if str(x).strip()
        ],
        integration_id=service.pk,
    )


def _service_qs(
    *, school, service_type: str | None = None, name_hints: list[str] | None = None
):
    qs = ServiceIntegration.objects.filter(school=school, is_active=True)
    if service_type:
        qs = qs.filter(service_type=service_type)
    hints = [str(h).strip().lower() for h in (name_hints or []) if str(h).strip()]
    if hints:
        q = None
        for hint in hints:
            clause = (
                Q(service_name__icontains=hint)
                | Q(endpoint_url__icontains=hint)
                | Q(config__icontains=hint)
            )
            q = clause if q is None else (q | clause)
        if q is not None:
            qs = qs.filter(q)
    return qs.order_by("-updated_at", "-id")


def _legacy_qs(*, school, name_hints: list[str] | None = None):
    qs = Integration.objects.filter(school=school, enabled=True)
    hints = [str(h).strip().lower() for h in (name_hints or []) if str(h).strip()]
    if hints:
        q = None
        for hint in hints:
            clause = (
                Q(name__icontains=hint)
                | Q(slug__icontains=hint)
                | Q(provider__icontains=hint)
                | Q(category__icontains=hint)
                | Q(config__icontains=hint)
            )
            q = clause if q is None else (q | clause)
        if q is not None:
            qs = qs.filter(q)
    return qs.order_by("-updated_at", "-id")


def _upsert_service_from_legacy(
    record: IntegrationRecord, *, school, legacy: Integration
) -> ServiceIntegration | None:
    if not record.service_name:
        return None
    service, _created = ServiceIntegration.objects.update_or_create(
        school=school,
        service_name=record.service_name,
        defaults={
            "service_type": record.service_type,
            "endpoint_url": record.endpoint_url,
            "enabled_scopes": record.enabled_scopes,
            "config": {
                **record.config,
                "_legacy_integration_id": legacy.pk,
                "_legacy_provider": legacy.provider,
                "_legacy_category": legacy.category,
            },
            "is_active": bool(legacy.enabled),
        },
    )
    return service


def resolve_active_integration(school, service_name: str) -> IntegrationRecord | None:
    """
    Resolve by service_name with ServiceIntegration as source of truth, then legacy fallback.
    """
    if school is None:
        return None
    key = str(service_name or "").strip()
    if not key:
        return None

    service = (
        ServiceIntegration.objects.filter(school=school, is_active=True)
        .filter(service_name__iexact=key)
        .order_by("-updated_at")
        .first()
    )
    if service:
        return _service_to_record(service)

    legacy = (
        Integration.objects.filter(school=school, enabled=True)
        .filter(slug__iexact=key)
        .order_by("-updated_at")
        .first()
    )
    if not legacy:
        legacy = (
            Integration.objects.filter(school=school, enabled=True)
            .filter(name__iexact=key)
            .order_by("-updated_at")
            .first()
        )
    if legacy:
        return _legacy_to_record(legacy)
    return None


def resolve_service_integration(
    school,
    *,
    service_type: str | None = None,
    service_name: str = "",
    name_hints: list[str] | None = None,
    allow_legacy_backfill: bool = True,
) -> ServiceIntegration | None:
    """
    Resolve an active ServiceIntegration.

    Resolution order:
    1) Active ServiceIntegration (exact service_name if provided, then hints)
    2) Legacy Integration fallback with optional auto-backfill into ServiceIntegration.
    """
    if school is None:
        return None

    exact = str(service_name or "").strip()
    if exact:
        qs = ServiceIntegration.objects.filter(school=school, is_active=True)
        if service_type:
            qs = qs.filter(service_type=service_type)
        item = (
            qs.filter(service_name__iexact=exact).order_by("-updated_at", "-id").first()
        )
        if item:
            return item

    hints = list(name_hints or [])
    if exact:
        hints = [exact, *hints]
    item = _service_qs(
        school=school, service_type=service_type, name_hints=hints
    ).first()
    if item:
        return item
    if not allow_legacy_backfill:
        return None

    legacy = _legacy_qs(school=school, name_hints=hints).first()
    if not legacy:
        return None
    record = _legacy_to_record(legacy)
    if service_type and record.service_type != service_type:
        return None
    return _upsert_service_from_legacy(record, school=school, legacy=legacy)


def backfill_service_integrations_from_legacy(
    *, school=None, dry_run: bool = False
) -> list[dict[str, Any]]:
    """
    Create/update ServiceIntegration records from legacy Integration rows.
    """
    qs = (
        Integration.objects.filter(enabled=True)
        .exclude(school__isnull=True)
        .select_related("school")
    )
    if school is not None:
        qs = qs.filter(school=school)

    results: list[dict[str, Any]] = []
    for legacy in qs:
        record = _legacy_to_record(legacy)
        if not record.service_name:
            continue
        payload = {
            "school_id": str(legacy.school_id),
            "legacy_id": legacy.pk,
            "service_name": record.service_name,
            "service_type": record.service_type,
        }
        if dry_run:
            payload["action"] = "would_upsert"
            results.append(payload)
            continue

        service, created = ServiceIntegration.objects.update_or_create(
            school=legacy.school,
            service_name=record.service_name,
            defaults={
                "service_type": record.service_type,
                "endpoint_url": record.endpoint_url,
                "enabled_scopes": record.enabled_scopes,
                "config": {
                    **record.config,
                    "_legacy_integration_id": legacy.pk,
                    "_legacy_provider": legacy.provider,
                    "_legacy_category": legacy.category,
                },
                "is_active": bool(legacy.enabled),
            },
        )
        payload["action"] = "created" if created else "updated"
        payload["service_id"] = service.pk
        results.append(payload)

    return results
