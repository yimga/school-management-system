"""
Metadata no-DDL safety: block schema mutations on request/worker hot paths.

Custom fields use DynamicFieldDefinition / DynamicFieldValue (EAV). Governed
preview/rollback flows live in platform_runtime.metadata_governance.
"""

from __future__ import annotations

import re
from typing import Any, Callable, TypeVar

from apps.platform_runtime.metadata_governance import (
    analyze_metadata_impact,
    build_metadata_change_set,
    preview_metadata_change_set,
)

_F = TypeVar("_F", bound=Callable[..., Any])

_DDL_PATTERNS = (
    re.compile(r"\bALTER\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bADD\s+COLUMN\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE),
)


class MetadataDdlForbiddenError(RuntimeError):
    """Raised when raw DDL is attempted on a metadata request path."""


def contains_forbidden_ddl(sql: str) -> bool:
    text = str(sql or "")
    if not text.strip():
        return False
    return any(pattern.search(text) for pattern in _DDL_PATTERNS)


def assert_no_ddl_in_sql(sql: str, *, context: str = "") -> None:
    if contains_forbidden_ddl(sql):
        label = f" ({context})" if context else ""
        raise MetadataDdlForbiddenError(f"Metadata paths forbid raw DDL{label}.")


def guard_metadata_request_path(fn: _F) -> _F:
    """Decorator: refuse if the wrapped callable receives obvious DDL in SQL args."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        for value in list(args) + list(kwargs.values()):
            if isinstance(value, str):
                assert_no_ddl_in_sql(value, context=fn.__name__)
        return fn(*args, **kwargs)

    wrapper.__name__ = getattr(fn, "__name__", "guarded")
    wrapper.__doc__ = fn.__doc__
    return wrapper  # type: ignore[return-value]


def preview_governed_metadata_change(
    changes: list[dict[str, Any]],
    *,
    scope: str = "tenant",
    tenant_id: str = "",
    current_version: str = "1.0",
    proposed_version: str = "1.1",
) -> dict[str, Any]:
    """Non-mutating preview + impact for operator metadata workflows."""
    change_set = build_metadata_change_set(
        changes,
        scope=scope,
        tenant_id=tenant_id,
        current_version=current_version,
        proposed_version=proposed_version,
    )
    preview = preview_metadata_change_set(
        change_set,
        tenant_context=tenant_id if scope == "tenant" else "",
    )
    impact = analyze_metadata_impact(change_set)
    return {
        "change_set": change_set,
        "preview": preview,
        "impact": impact,
        "rollback_posture": change_set.get("rollback_coverage", {}),
        "non_mutating": True,
    }


__all__ = [
    "MetadataDdlForbiddenError",
    "assert_no_ddl_in_sql",
    "contains_forbidden_ddl",
    "guard_metadata_request_path",
    "preview_governed_metadata_change",
]
