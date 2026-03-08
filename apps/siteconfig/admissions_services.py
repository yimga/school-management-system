"""
Phase 6: Admissions services — consume request.tenant_runtime.modules.admissions only.
Use these instead of SiteSettings or hardcoded country/level/document lists.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def get_admissions_config(runtime: Any) -> Dict[str, Any]:
    """Return runtime.modules.admissions or empty dict."""
    if runtime is None:
        return {}
    modules = getattr(runtime, "modules", None)
    if modules is None:
        return {}
    return getattr(modules, "admissions", None) or {}


def get_education_levels_for_admissions(runtime: Any) -> List[Dict[str, Any]]:
    """Education levels for admission forms; from runtime.registry or modules.admissions."""
    if runtime is None:
        return []
    reg = getattr(runtime, "registry", None)
    if reg and getattr(reg, "education_levels", None):
        return list(reg.education_levels)
    cfg = get_admissions_config(runtime)
    return cfg.get("education_levels") or cfg.get("education_level_options") or []


def get_required_documents(runtime: Any) -> List[str]:
    """Required document type codes for applications."""
    cfg = get_admissions_config(runtime)
    return list(cfg.get("required_documents") or [])


def get_optional_documents(runtime: Any) -> List[str]:
    """Optional document type codes."""
    cfg = get_admissions_config(runtime)
    return list(cfg.get("optional_documents") or [])


def get_numbering_strategy(runtime: Any) -> str:
    """Admission number strategy: sequential, campus_year_sequence, etc."""
    cfg = get_admissions_config(runtime)
    return (cfg.get("numbering_strategy") or "sequential").lower()


def get_admissions_workflow(runtime: Any) -> Optional[Dict[str, Any]]:
    """Admissions workflow definition from runtime.modules.admissions.workflow."""
    cfg = get_admissions_config(runtime)
    return cfg.get("workflow")
