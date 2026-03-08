"""
Phase 10: Migration Cloud — registry-aware mapping and validation stubs.
Use MigrationMappingService, MigrationValidationService for dry-run and cutover.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def map_education_level(source_code: str, target_country: str, runtime: Any = None) -> Optional[str]:
    """Map source education level to registry code for target country. Stub."""
    return source_code


def map_grade_scale(source_scale: str, target_country: str, runtime: Any = None) -> Optional[str]:
    """Map source grading scale to registry grade_scale_family. Stub."""
    return source_scale


def map_fee_category(source_code: str, target_country: str, runtime: Any = None) -> Optional[str]:
    """Map source fee category to registry fee_categories. Stub."""
    return source_code


def validate_migration_mapping(mapping: Dict[str, Any], school: Any = None) -> List[str]:
    """Validate a migration mapping against registries; return list of warnings/errors. Stub."""
    return []


def dry_run_import(source_profile: str, payload: Dict[str, Any], school: Any = None) -> Dict[str, Any]:
    """Non-destructive dry run of import. Returns summary and validation result. Stub."""
    return {"ok": True, "warnings": [], "rows_affected": 0}
