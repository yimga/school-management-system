"""v4.00.36 — billing AppConfig.

Created to host the ``ready()`` hook for storage metering signal wiring.
Up to this point the billing app used Django's default ``AppConfig`` —
that's still fine for everything else, this just adds a load-time hook.
"""

from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing"
    label = "billing"
    verbose_name = "Billing"

    def ready(self) -> None:  # pragma: no cover - imports at app load
        # v4.00.36: ensure the worker registers our @shared_task functions at
        # startup. Celery's autodiscover_tasks() only walks <app>.tasks; these
        # live in tasks_ai_token_flush.py / realtime_meter.py so we import
        # them explicitly here. Side-effect-only — no symbol use.
        try:
            from . import tasks_ai_token_flush  # noqa: F401
            from . import realtime_meter  # noqa: F401
        except (ImportError, RuntimeError):
            pass

        try:
            from django.apps import apps as django_apps
            from .storage_metering import connect_storage_metering

            # File-bearing finance models opted into storage metering.
            # ADD A LINE HERE when adding a new FileField that should bill
            # toward the tenant's storage_bytes meter. Each entry is
            # (model_label, file_field_attr_name). Other apps can opt in
            # by calling connect_storage_metering(...) from their own
            # AppConfig.ready hook — no central registration required.
            for label, field_name in (
                ("finance.Invoice", "payment_proof"),
                ("finance.Invoice", "attachment"),
                ("finance.Payment", "receipt_file"),
            ):
                app_label, model_name = label.split(".")
                try:
                    model_cls = django_apps.get_model(app_label, model_name)
                except LookupError:
                    continue
                if model_cls is None:
                    continue
                try:
                    connect_storage_metering(model_cls, file_field_name=field_name)
                except (AttributeError, RuntimeError, ValueError) as exc:
                    logger.debug(
                        "storage metering wire failed for %s.%s: %s",
                        label,
                        field_name,
                        exc,
                    )
        except (ImportError, RuntimeError) as exc:
            logger.debug("storage metering wiring skipped at ready(): %s", exc)
