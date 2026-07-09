import logging
import os
import threading
from typing import Optional

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError

from .preview_state import is_preview_mode

logger = logging.getLogger(__name__)


OPTIONAL_DB_ROUTER_ERRORS = (
    AttributeError,
    DatabaseError,
    ImportError,
    RuntimeError,
    TypeError,
    ValueError,
)

# Reentrancy guard for the residency check: the check itself performs ORM ops
# (region resolution reads RuntimeDefaults; a violation writes an AuditLog
# row), and each of those re-enters db_for_read/db_for_write. Without the
# guard that recursion is unbounded (audit → router → audit → …).
_residency_guard = threading.local()


def _residency_enforce_flag() -> bool:
    """Deliberately import-free duplicate of ``residency_enforced``.

    The fail-closed arm below must be able to answer "is enforcement on?"
    even when the compliance module whose failure it is handling cannot be
    imported — so it reads the env/setting directly instead of delegating.
    """
    if os.environ.get("DATA_RESIDENCY_ENFORCE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return True
    return bool(getattr(settings, "DATA_RESIDENCY_ENFORCE", False))


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
    ``connection.tenant`` (the only context the router has). No-op when
    ``DATA_RESIDENCY_ENFORCE`` is off (the backward-compatible default) or when
    there is no tenant to compare.

    Unresolvable-region closeout (2026-07-09): a missing ``alias`` no longer
    skips the check — it means the op is served by the DEFAULT store, so it is
    adjudicated against the declared default-store region
    (``region_for_alias`` → ``default_store_region``). In-region/global
    tenants keep working with zero replicas provisioned; a tenant with a
    foreign residency promise fails closed instead of silently landing
    out-of-region. Likewise a plumbing failure while enforcement is on now
    DENIES (mirrors ``pdp_enforce``) instead of silently skipping the check.
    Application-layer control — physical per-region replicas remain an
    ops/deploy item; this fails the op closed until they exist.
    """
    if not _residency_enforce_flag():
        return
    if getattr(_residency_guard, "active", False):
        # Reentrant ORM op issued BY the in-flight residency check itself
        # (region resolution read / violation audit write) — adjudicating it
        # would recurse; the outer check's verdict governs the request.
        return
    try:
        from django.db import connection

        tenant = getattr(connection, "tenant", None)
        school = getattr(tenant, "school", None) if tenant is not None else None
        if school is None:
            return
        from apps.compliance.cross_border_export import enforce_region_match
        from apps.schools.data_residency import region_for_alias

        _residency_guard.active = True
        try:
            enforce_region_match(school, region_for_alias(alias), kind="db_route")
        finally:
            _residency_guard.active = False
    except OPTIONAL_DB_ROUTER_ERRORS:
        # The ResidencyViolation raised by enforce_region_match is NOT in this
        # tuple, so a genuine cross-region block always propagates. Anything
        # here is broken plumbing — under enforcement that must fail CLOSED
        # (a residency decision we cannot compute is not permission), while
        # the flag-off posture stays no-op. The flag is re-read import-free
        # because the failure being handled may BE the compliance import.
        if _residency_enforce_flag():
            logger.error(
                "residency: enforcement plumbing failed for alias=%r — denying (fail closed)",
                alias,
                exc_info=True,
            )
            raise PermissionDenied("Data residency decision unavailable")
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
