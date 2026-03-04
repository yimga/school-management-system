from typing import Optional

from django.conf import settings

from .preview_state import is_preview_mode


def _get_tenant_db_alias() -> Optional[str]:
    """
    World Engine: return DB alias for current tenant when multi-DB is configured.
    Uses Client.db_alias, or School.dedicated_db_alias / School.regional_cluster.
    """
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
    except Exception:
        pass
    return None


def _get_read_replica_alias() -> Optional[str]:
    """World Engine: read replica for reporting/dashboard when configured (195-country scale)."""
    alias = getattr(settings, "DATABASE_READ_REPLICA_ALIAS", None)
    if alias and alias in getattr(settings, "DATABASES", {}):
        return alias
    return None


class TenantDatabaseRouter:
    """
    World Engine: route tenant reads/writes by Tenant.db_alias or School.dedicated_db_alias/regional_cluster.
    Read/write split: when DATABASE_READ_REPLICA_ALIAS is set, reads use replica; writes use primary.
    """
    def db_for_read(self, model, **hints) -> Optional[str]:
        replica = _get_read_replica_alias()
        if replica:
            return replica
        return _get_tenant_db_alias()

    def db_for_write(self, model, **hints) -> Optional[str]:
        return _get_tenant_db_alias()

    def allow_relation(self, obj1, obj2, **hints) -> Optional[bool]:
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints) -> bool:
        return True


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
