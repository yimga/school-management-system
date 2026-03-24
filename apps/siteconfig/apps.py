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
        # Default Django admin site only; manager and tenant urlconfs use config.admin.admin_site
        # (RunMyCampusAdminSite), which has login_template = "auth/admin_login.html" for the high-end
        # superadmin login. This assignment affects django.contrib.admin.site if used elsewhere.
        admin.site.login_template = "auth/login.html"
