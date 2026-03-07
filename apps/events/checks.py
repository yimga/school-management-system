from django.core.checks import Warning, register


@register()
def legacy_webhook_stack_check(app_configs, **kwargs):
    from apps.events.legacy_bridge import legacy_webhook_sync_snapshot

    snapshot = legacy_webhook_sync_snapshot()
    legacy_groups = int(snapshot.get("legacy_groups", 0))
    legacy_active_groups = int(snapshot.get("legacy_active_groups", 0))
    unsynced_groups = int(snapshot.get("unsynced_legacy_groups", 0))
    if legacy_groups <= 0 or (legacy_active_groups <= 0 and unsynced_groups <= 0):
        return []

    sample_urls = snapshot.get("sample_unsynced_urls") or []
    sample_hint = f" Sample URLs: {', '.join(sample_urls[:3])}." if sample_urls else ""

    return [
        Warning(
            (
                "Legacy siteconfig webhook subscriptions are still present alongside the canonical "
                f"apps.events webhook stack ({legacy_groups} grouped legacy subscriptions, "
                f"{legacy_active_groups} active legacy groups, {unsynced_groups} unsynced groups)."
            ),
            hint=(
                "Run `python manage.py retire_legacy_webhooks` to sync and deactivate legacy producers "
                f"before treating apps.events as the only delivery authority.{sample_hint}"
            ),
            id="events.W001",
        )
    ]
