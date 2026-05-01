"""
Governed operational query layer — ORM-only, tenant + permission scoped.

Operators never submit SQL; all columns and filters are allowlisted in ``catalog``.
"""

from .catalog import DATASETS, list_dataset_ids, max_export_rows
from .executor import GovernedQueryError, execute_governed_query, serialize_catalog_for_ui
from .audit import log_governed_export_event

__all__ = [
    "DATASETS",
    "GovernedQueryError",
    "execute_governed_query",
    "list_dataset_ids",
    "log_governed_export_event",
    "max_export_rows",
    "serialize_catalog_for_ui",
]
