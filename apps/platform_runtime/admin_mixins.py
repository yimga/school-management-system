"""
Cross-cutting admin mixins — reusable defaults so individual ModelAdmin classes
don't have to hardcode pagination, defaults, etc.

See `docs/CONFIGURABILITY.md` (Layer B + Layer G) for the contract.
"""
from django.conf import settings


class TenantPaginationMixin:
    """Apply the platform-configured admin page size to any ModelAdmin.

    Replaces 35+ hardcoded `list_per_page = 50` (etc.) across apps.

    Override per-app: subclass and set `list_per_page = settings.DEFAULT_AUDIT_PAGE_SIZE`
    if a denser/sparser default suits that surface.
    """

    @property
    def list_per_page(self):  # type: ignore[override]
        return getattr(settings, "DEFAULT_ADMIN_PAGE_SIZE", 50)

    @property
    def list_max_show_all(self):  # type: ignore[override]
        # Default Django value is 200; allow it to scale with admin page size.
        return getattr(settings, "DEFAULT_ADMIN_PAGE_SIZE", 50) * 4


class AuditPaginationMixin(TenantPaginationMixin):
    """Wider default for audit / compliance lists where the operator wants depth."""

    @property
    def list_per_page(self):  # type: ignore[override]
        return getattr(settings, "DEFAULT_AUDIT_PAGE_SIZE", 100)
