"""
Communication App Configuration
"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CommunicationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.communication"
    verbose_name = "Communication"

    def ready(self) -> None:
        """Pillar 3 — Verified Communications: gate DKIM signing posture.

        Soft-warns in development; raises in production when
        ``EMAIL_SIGNING_REQUIRED=True`` and no DKIM-signing backend is
        wired. See ``apps.communication.email_signing`` for the
        provider matrix and DNS-record runbook.
        """
        # Imported lazily so app-loading order can never break test
        # discovery (the module touches django.conf.settings, which is
        # safe at ready() time but not at import time of apps.py).
        from .email_signing import EmailSigningMisconfigured, assert_dkim_configured

        try:
            assert_dkim_configured()
        except EmailSigningMisconfigured:
            # Re-raise: deploy must fail loudly when production posture
            # is declared but the backend cannot honor it.
            raise
        except Exception as exc:  # noqa: BLE001 — defensive ready() guard
            # Any unexpected failure (e.g. settings module half-loaded
            # in a degenerate test bootstrap) must not crash app init.
            logger.warning("email signing posture check skipped: %s", exc)
