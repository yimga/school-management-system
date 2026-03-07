"""
TenantContext: immutable context attached to every request (request.tenant_ctx).
Built from request.school (RLS mode) or request.tenant (schema mode).
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TenantContext:
    """Single entry point for tenant identity and policy-related data."""
    tenant_id: str
    schema_name: Optional[str]
    school_id: Optional[Any]  # School.id is UUID in this codebase
    country: Optional[str]
    timezone: Optional[str]
    feature_flags: Dict[str, Any]
    policy_overrides: Dict[str, Any]
    host: str

    @classmethod
    def empty(cls, host: str = "") -> "TenantContext":
        """No tenant (public/base domain)."""
        return cls(
            tenant_id="",
            schema_name=None,
            school_id=None,
            country=None,
            timezone=None,
            feature_flags={},
            policy_overrides={},
            host=host or "",
        )

    @property
    def is_tenant(self) -> bool:
        return bool(self.tenant_id or self.school_id)
