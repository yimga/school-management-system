from __future__ import annotations

from collections import defaultdict
from django.db.utils import OperationalError, ProgrammingError


def _normalize_event_types(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    normalized = [str(item).strip() for item in raw if str(item).strip()]
    return sorted(dict.fromkeys(normalized))


def _legacy_groups() -> list[dict]:
    from apps.siteconfig.models_platform_catalog import (
        WebhookSubscription as LegacyWebhookSubscription,
    )

    grouped: dict[tuple[str, str, str], dict] = {}
    try:
        queryset = LegacyWebhookSubscription.objects.select_related("school").order_by(
            "school_id",
            "target_url",
            "secret",
            "event_type",
        )
        for subscription in queryset:
            key = (
                str(subscription.school_id or ""),
                str(subscription.target_url or "").strip(),
                str(subscription.secret or "").strip(),
            )
            bucket = grouped.setdefault(
                key,
                {
                    "school_id": subscription.school_id,
                    "url": str(subscription.target_url or "").strip(),
                    "secret": str(subscription.secret or "").strip(),
                    "event_types": set(),
                    "is_active": False,
                },
            )
            event_type = str(subscription.event_type or "").strip()
            if event_type:
                bucket["event_types"].add(event_type)
            bucket["is_active"] = bool(bucket["is_active"] or subscription.is_active)
    except (OperationalError, ProgrammingError):
        return []

    groups: list[dict] = []
    for bucket in grouped.values():
        groups.append(
            {
                "school_id": bucket["school_id"],
                "url": bucket["url"],
                "secret": bucket["secret"],
                "event_types": sorted(bucket["event_types"]),
                "is_active": bool(bucket["is_active"]),
            }
        )
    return groups


def _canonical_groups() -> dict[tuple[str, str, str], dict]:
    from apps.events.models import WebhookSubscription

    grouped: dict[tuple[str, str, str], dict] = {}
    try:
        for subscription in WebhookSubscription.objects.all().order_by(
            "school_id", "url", "secret"
        ):
            key = (
                str(subscription.school_id or ""),
                str(subscription.url or "").strip(),
                str(subscription.secret or "").strip(),
            )
            grouped[key] = {
                "school_id": subscription.school_id,
                "url": str(subscription.url or "").strip(),
                "secret": str(subscription.secret or "").strip(),
                "event_types": _normalize_event_types(subscription.event_types),
                "is_active": bool(subscription.is_active),
                "subscription_id": subscription.pk,
            }
    except (OperationalError, ProgrammingError):
        return {}
    return grouped


def legacy_webhook_sync_snapshot() -> dict:
    legacy_groups = _legacy_groups()
    canonical_groups = _canonical_groups()
    unsynced_groups = 0
    sample_unsynced_urls: list[str] = []

    for group in legacy_groups:
        key = (
            str(group["school_id"] or ""),
            group["url"],
            group["secret"],
        )
        canonical = canonical_groups.get(key)
        if not canonical:
            unsynced_groups += 1
            if len(sample_unsynced_urls) < 5:
                sample_unsynced_urls.append(group["url"])
            continue

        if not set(group["event_types"]).issubset(set(canonical["event_types"])):
            unsynced_groups += 1
            if len(sample_unsynced_urls) < 5:
                sample_unsynced_urls.append(group["url"])

    return {
        "legacy_groups": len(legacy_groups),
        "legacy_active_groups": sum(1 for group in legacy_groups if group["is_active"]),
        "canonical_groups": len(canonical_groups),
        "canonical_active_groups": sum(
            1 for group in canonical_groups.values() if group["is_active"]
        ),
        "unsynced_legacy_groups": unsynced_groups,
        "sample_unsynced_urls": sample_unsynced_urls,
    }


def sync_legacy_webhook_subscriptions(*, dry_run: bool = False) -> dict:
    from apps.events.models import WebhookSubscription

    summary = defaultdict(int)
    for group in _legacy_groups():
        desired_event_types = group["event_types"]
        existing = (
            WebhookSubscription.objects.filter(
                school_id=group["school_id"],
                url=group["url"],
                secret=group["secret"],
            )
            .order_by("created_at", "id")
            .first()
        )

        if existing is None:
            summary["created"] += 1
            if not dry_run:
                WebhookSubscription.objects.create(
                    school_id=group["school_id"],
                    url=group["url"],
                    secret=group["secret"],
                    event_types=desired_event_types,
                    is_active=group["is_active"],
                    description="Synced from legacy siteconfig webhook subscriptions.",
                )
            continue

        changed_fields = []
        if _normalize_event_types(existing.event_types) != desired_event_types:
            existing.event_types = desired_event_types
            changed_fields.append("event_types")
        if bool(existing.is_active) != bool(group["is_active"]):
            existing.is_active = bool(group["is_active"])
            changed_fields.append("is_active")
        if not str(existing.description or "").strip():
            existing.description = (
                "Synced from legacy siteconfig webhook subscriptions."
            )
            changed_fields.append("description")

        if changed_fields:
            summary["updated"] += 1
            if not dry_run:
                existing.save(update_fields=changed_fields + ["updated_at"])
        else:
            summary["unchanged"] += 1

    snapshot = legacy_webhook_sync_snapshot()
    return {
        "created": int(summary["created"]),
        "updated": int(summary["updated"]),
        "unchanged": int(summary["unchanged"]),
        "legacy_groups": snapshot["legacy_groups"],
        "unsynced_legacy_groups": snapshot["unsynced_legacy_groups"],
    }


def retire_legacy_webhook_subscriptions(*, dry_run: bool = False) -> dict:
    from apps.siteconfig.models_platform_catalog import (
        WebhookSubscription as LegacyWebhookSubscription,
    )

    sync_summary = sync_legacy_webhook_subscriptions(dry_run=dry_run)
    active_qs = LegacyWebhookSubscription.objects.filter(is_active=True)
    active_count = active_qs.count()
    if active_count and not dry_run:
        active_qs.update(is_active=False)
    snapshot = legacy_webhook_sync_snapshot()
    return {
        **sync_summary,
        "retired_active_subscriptions": int(active_count),
        "remaining_active_legacy_groups": int(
            snapshot.get("legacy_active_groups", 0) if dry_run else 0
        ),
    }
