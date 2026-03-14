"""
Section 8.7–8.8: Health check and resource hogs (PG metadata).
Delegates to repositories.health_repository for all raw SQL (§2.4 raw_sql_replacement_targets).
"""
from apps.schools.repositories.health_repository import (
    get_global_health_stats as _get_global_health_stats,
    get_top_tables_by_size as _get_top_tables_by_size,
)


def get_top_tables_by_size(limit=10, schema_name=None):
    """Thin wrapper; implementation in repositories.health_repository."""
    return _get_top_tables_by_size(limit=limit, schema_name=schema_name)


def get_global_health_stats():
    """Thin wrapper; implementation in repositories.health_repository."""
    return _get_global_health_stats()
