from typing import Optional

from django.conf import settings
from django.db import DatabaseError

from .preview_state import is_preview_mode


OPTIONAL_DB_ROUTER_ERRORS = (
    AttributeError,
    DatabaseError,
    ImportError,
    RuntimeError,
    TypeError,
    ValueError,
)


def _get_tenant_db_alias() -> Optional[str]:
    """
    World Engine: return DB alias for current tenant when multi-DB is configured.
    Uses Client.db_alias, or School.dedicated_db_alias / School.regional_cluster.
    """
    try:
        from apps.platform_runtime.dynamic_db_routing import effective_db_alias

        override = effective_db_alias()
        if override:
            return override
    except OPTIONAL_DB_ROUTER_ERRORS:
        pass
    try:
        from django.db import connection

        tenant = getattr(connection, "tenant", None)
        if not tenant:
            return None
        alias = getattr(tenant, "db_alias", None) or ""
        if alias and alias.strip():
            if alias.strip() in settings.DATABASES:
                return alias.strip()
        school = getattr(tenant, "school", None)
        if school:
            dedicated = getattr(school, "dedicated_db_alias", None) or ""
            if dedicated.strip() and dedicated.strip() in settings.DATABASES:
                return dedicated.strip()
            region = getattr(school, "regional_cluster", None) or ""
            if region.strip() and region.strip() in settings.DATABASES:
                return region.strip()
    except OPTIONAL_DB_ROUTER_ERRORS:
        pass
    return None


def _get_read_replica_alias() -> Optional[str]:
    """World Engine: read replica for reporting/dashboard when configured (195-country scale)."""
    alias = getattr(settings, "DATABASE_READ_REPLICA_ALIAS", None)
    if alias and alias in getattr(settings, "DATABASES", {}):
        return alias
    return None


def _enforce_residency_for_alias(alias: Optional[str]) -> None:
    """Border-lock (metric #27): block a cross-region tenant DB op when strict.

    The router is the single choke point every ORM read/write flows through, so
    it is where a region-A tenant resolving to a region-B store is actually
    *blocked* (raising the typed ``ResidencyViolation`` → HTTP 403, audited)
    rather than merely preferring an alias. The active tenant is read from
    ``connection.tenant`` (the only context the router has); ``alias`` is the
    region the op would be served from. No-op when ``DATA_RESIDENCY_ENFORCE``
    is off (the backward-compatible default) or when there is no tenant/alias
    to compare. Application-layer control — physical per-region replicas remain
    an ops/deploy item; this fails the op closed until they exist.
    """
    if not alias:
        return
    try:
        from django.db import connection

        tenant = getattr(connection, "tenant", None)
        school = getattr(tenant, "school", None) if tenant is not None else None
        if school is None:
            return
        from apps.compliance.cross_border_export import enforce_region_match

        enforce_region_match(school, alias, kind="db_route")
    except OPTIONAL_DB_ROUTER_ERRORS:
        # Resolution plumbing failed — never convert that into a spurious block;
        # the ResidencyViolation raised by enforce_region_match is NOT in this
        # tuple, so a genuine cross-region violation still propagates.
        return


class TenantDatabaseRouter:
    """
    World Engine: route tenant reads/writes by Tenant.db_alias or School.dedicated_db_alias/regional_cluster.
    Read/write split: when DATABASE_READ_REPLICA_ALIAS is set, reads use replica; writes use primary.

    Border-lock: under ``settings.DATA_RESIDENCY_ENFORCE`` the resolved alias is
    checked against the active tenant's regulatory region; an out-of-region
    read/write raises ``ResidencyViolation`` instead of silently crossing the
    border (no-op when the flag is off).
    """

    def db_for_read(self, model, **hints) -> Optional[str]:
        replica = _get_read_replica_alias()
        if replica:
            # A read replica is an operational read-split, not a regional
            # binding, so it is not residency-checked here. The tenant alias
            # below (which carries the region) is the residency choke point.
            return replica
        alias = _get_tenant_db_alias()
        _enforce_residency_for_alias(alias)
        return alias

    def db_for_write(self, model, **hints) -> Optional[str]:
        alias = _get_tenant_db_alias()
        _enforce_residency_for_alias(alias)
        return alias

    def allow_relation(self, obj1, obj2, **hints) -> Optional[bool]:
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints) -> Optional[bool]:
        """
        Defer migration routing to downstream routers.

        In schema mode, django-tenants' TenantSyncRouter must decide whether an app
        belongs in the public schema or tenant schemas. Returning True here causes
        tenant-app migrations to run during `migrate_schemas --shared`.
        """
        return None


class PreviewDatabaseRouter:
    """Route requests marked as preview to the sandbox database."""

    preview_db = "preview"
    default_db = "default"

    def _use_preview(self) -> bool:
        return is_preview_mode()

    def db_for_read(self, model, **hints) -> Optional[str]:
        return self.preview_db if self._use_preview() else None

    def db_for_write(self, model, **hints) -> Optional[str]:
        return self.preview_db if self._use_preview() else None

    def allow_relation(self, obj1, obj2, **hints) -> Optional[bool]:
        if not self._use_preview():
            return None
        db1 = getattr(obj1._state, "db", self.default_db)
        db2 = getattr(obj2._state, "db", self.default_db)
        return db1 == self.preview_db and db2 == self.preview_db

    def allow_migrate(self, db, app_label, model_name=None, **hints) -> bool:
        if self._use_preview():
            return db == self.preview_db
        return db == self.default_db
