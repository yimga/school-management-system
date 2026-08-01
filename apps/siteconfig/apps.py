import logging

from django.apps import AppConfig
from django.contrib import admin


logger = logging.getLogger(__name__)


class SiteconfigConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.siteconfig"
    verbose_name = "⚙️ Configuration Control Center"

    def ready(self):
        # Ensure additional dashboard and workflow models are imported for migrations
        try:
            from . import models_dashboard  # noqa: F401
        except (
            AttributeError,
            ImportError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            logger.debug("Optional siteconfig dashboard models import skipped: %s", exc)
        try:
            from . import models_workflow  # noqa: F401
        except (
            AttributeError,
            ImportError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            logger.debug("Optional siteconfig workflow models import skipped: %s", exc)
        try:
            from . import models_ai  # noqa: F401 — Phase 10 — 2.1 decomposition
        except (
            AttributeError,
            ImportError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            logger.debug("Optional siteconfig AI models import skipped: %s", exc)
        # Import signals for audit logging and pack assignment -> PackageEngine
        try:
            from . import signals  # noqa: F401
            from .signals import _connect_pack_assignment_signals

            _connect_pack_assignment_signals()
        except (
            AttributeError,
            ImportError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            logger.warning("Siteconfig signal wiring skipped: %s", exc)
        # v4.00.45 — public status page subscriber fan-out on PublicIncident save.
        try:
            from .signals_public_status import _connect_public_incident_signals

            _connect_public_incident_signals()
        except (
            AttributeError,
            ImportError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            logger.warning("Siteconfig public-incident signal wiring skipped: %s", exc)
        # Register the custom-domain background tasks so the beat entry
        # `siteconfig-sweep-pending-custom-domains` names a LIVE task. The
        # @shared_tasks live in tasks_custom_domain.py (NOT tasks.py), so bare
        # Celery autodiscover never imported them and the sweep silently never
        # fired — a tenant's DNS-verified custom domain therefore never
        # activated. Importing here (like the models/signals above) registers
        # siteconfig.sweep_pending_custom_domains + siteconfig.verify_custom_domain
        # before the beat scheduler reads the registry. The sweep only does
        # read-only DNS TXT checks and flips is_verified; no cert/provisioning
        # or other outbound side effects.
        try:
            from . import tasks_custom_domain  # noqa: F401
        except (
            AttributeError,
            ImportError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            logger.warning(
                "Siteconfig custom-domain task registration skipped: %s", exc
            )
        # Default Django admin site only; manager and tenant urlconfs use config.admin.admin_site
        # (RunMyCampusAdminSite), which has login_template = "auth/admin_login.html" for the high-end
        # superadmin login. This assignment affects django.contrib.admin.site if used elsewhere.
        admin.site.login_template = "auth/login.html"
