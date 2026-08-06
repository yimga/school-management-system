from django.apps import AppConfig


class IntegrationsMarketplaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integrations_marketplace"
    verbose_name = (
        "Integrations & Marketplace (providers, connectors, install metadata)"
    )

    def ready(self) -> None:
        # v2.79 — pull webhook handlers in so the `@register_webhook_handler`
        # decorators run. Without this the WEBHOOK_HANDLERS dict stays empty
        # and the inbound receiver always falls through to "no handler" / 204.
        # Import is wrapped because contributors may opt connectors in/out by
        # editing webhook_handlers.py and a transient ImportError shouldn't
        # crash the worker boot.
        try:
            from apps.integrations_marketplace import webhook_handlers  # noqa: F401
        except Exception:  # noqa: BLE001 — log + continue, handlers are best-effort
            import logging
            logging.getLogger(__name__).exception(
                "integrations_marketplace: failed to import webhook_handlers"
            )

        # v3.4 — wire the auto-subscribe receiver to `connector_connected` so
        # a successful OAuth dance triggers the upstream push-subscription.
        try:
            from apps.integrations_marketplace import subscription_subscribe  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "integrations_marketplace: failed to wire auto-subscribe"
            )

        # Inverse of auto-subscribe: wire the `connector_disconnected` receiver
        # so disconnecting a connector STOPS its upstream push channel (else
        # Google keeps hitting a dead webhook and the renewer rotates a ghost
        # subscription) and scrubs the row's stored OAuth secrets.
        try:
            from apps.integrations_marketplace import subscription_teardown  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "integrations_marketplace: failed to wire subscription teardown"
            )

        # v2.79 — bind Celery `task_prerun` / `task_postrun` signal handlers so
        # async sends pick up the per-task tenant context (the middleware does
        # this for sync request flow; tasks need a parallel hook).
        try:
            from apps.integrations_marketplace import celery_tenant_binding  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "integrations_marketplace: failed to bind celery tenant signals"
            )

        # v4.00.53 — import LMS token-refresh sweep so the @shared_task
        # registers with Celery before the beat scheduler reads the registry.
        try:
            from apps.integrations_marketplace import lms_token_refresh  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "integrations_marketplace: failed to import lms_token_refresh"
            )

        # v4.00.54 — import LMS token-ROTATION sweep so the @shared_task
        # registers with Celery before the beat scheduler reads the registry.
        try:
            from apps.integrations_marketplace import lms_token_rotation  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "integrations_marketplace: failed to import lms_token_rotation"
            )

        # v4.00.54 — import LMS audit-log retention sweep so the
        # @shared_task registers with Celery before the beat scheduler
        # reads the registry.
        try:
            from apps.integrations_marketplace import lms_audit_retention  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "integrations_marketplace: failed to import lms_audit_retention"
            )

        # v4.00.59 — LMS OAuth health beat: reactive auto-refresh of expired
        # tokens + audit-ring attach.
        try:
            from apps.integrations_marketplace import lms_oauth_health  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "integrations_marketplace: failed to import lms_oauth_health"
            )

        # v4.00.60 — LMS OAuth auto-prune on refresh_revoked: clears both
        # tokens when upstream OAuth returns invalid_grant / 400 / 401 / 403.
        try:
            from apps.integrations_marketplace import lms_oauth_auto_prune  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "integrations_marketplace: failed to import lms_oauth_auto_prune"
            )

        # v4.00.63 — LMSDiagActionAudit retention sweep (7y FERPA default).
        # Mirrors v4.00.54's lms_audit_retention pattern for the v4.00.62
        # dedicated diagnostics-action table.
        try:
            from apps.integrations_marketplace import lms_diag_action_retention  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "integrations_marketplace: failed to import lms_diag_action_retention"
            )

        # Calendar event-sync beat: import so the @shared_task
        # `integrations_marketplace.sync_calendar_events` registers with Celery
        # before the beat scheduler reads the registry (bare autodiscover only
        # imports <app>/tasks.py). Pairs with the beat entry in settings.
        try:
            from apps.integrations_marketplace import calendar_sync  # noqa: F401
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "integrations_marketplace: failed to import calendar_sync"
            )

        # Generic connected-mailbox sweeper beats (OAuth token refresh, mailbox
        # fetch, push-subscription renewal). Their @shared_task lives outside an
        # autodiscovered tasks.py, so importing here registers the names before
        # the beat scheduler reads the registry — otherwise the beat entries are
        # silent no-ops. Each wrapper is OUTBOUND and self-gated OFF by default
        # (INTEGRATIONS_MARKETPLACE_OUTBOUND_SWEEPS_ENABLED); the beat drain
        # no-ops until an operator enables marketplace mailbox integrations.
        for _sweep_module in (
            "token_refresh",
            "mailbox_fetch",
            "subscription_renewal",
        ):
            try:
                __import__(f"apps.integrations_marketplace.{_sweep_module}")
            except Exception:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).exception(
                    "integrations_marketplace: failed to import %s", _sweep_module
                )

        # v2.79 — startup advisory check: warn if OAUTH_CALLBACK_BASE_URL is
        # unset in a production-looking environment so operators don't ship a
        # broken OAuth dance silently.
        try:
            from apps.integrations_marketplace.startup_checks import (
                warn_if_oauth_callback_base_url_missing,
            )

            warn_if_oauth_callback_base_url_missing()
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception(
                "integrations_marketplace: startup advisory check crashed"
            )
