"""Phase 6 turbo runtime: cross-vertical kernel.

Provides an abstract Tenant / Org / ContextProfile registration surface that
demonstrably accepts non-education verticals without forking the core. The
alternate-vertical smoke pack exercises a health-vertical tenant and a
government-vertical tenant under the same kernel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-cross-vertical-kernel"
CONTRACT_TITLE = "Cross-vertical kernel"

ALLOWED_VERTICALS: tuple[str, ...] = ("education", "health", "government", "finance", "ngo")


class CrossVerticalKernelError(ValueError):
    """Raised when a verticality contract is violated."""


@dataclass(frozen=True)
class KernelTenant:
    tenant_id: str
    vertical: str
    name: str
    terminology_overlay: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KernelOrg:
    org_id: str
    vertical: str
    name: str


@dataclass(frozen=True)
class ContextProfile:
    profile_id: str
    tenant_id: str
    roles: tuple[str, ...]


class GovernanceKernel:
    def __init__(self) -> None:
        self._tenants: dict[str, KernelTenant] = {}
        self._orgs: dict[str, KernelOrg] = {}
        self._memberships: dict[str, set[str]] = {}
        self._context_profiles: dict[str, ContextProfile] = {}

    def register_tenant(self, tenant: KernelTenant) -> None:
        if tenant.vertical not in ALLOWED_VERTICALS:
            raise CrossVerticalKernelError(f"vertical_not_allowed:{tenant.vertical}")
        self._tenants[tenant.tenant_id] = tenant

    def register_org(self, org: KernelOrg) -> None:
        if org.vertical not in ALLOWED_VERTICALS:
            raise CrossVerticalKernelError(f"vertical_not_allowed:{org.vertical}")
        self._orgs[org.org_id] = org

    def link(self, tenant_id: str, org_id: str) -> None:
        if tenant_id not in self._tenants or org_id not in self._orgs:
            raise CrossVerticalKernelError("link_requires_existing_tenant_and_org")
        if self._tenants[tenant_id].vertical != self._orgs[org_id].vertical:
            raise CrossVerticalKernelError("vertical_mismatch_between_tenant_and_org")
        self._memberships.setdefault(org_id, set()).add(tenant_id)

    def register_context_profile(self, profile: ContextProfile) -> None:
        if profile.tenant_id not in self._tenants:
            raise CrossVerticalKernelError("context_profile_requires_existing_tenant")
        self._context_profiles[profile.profile_id] = profile

    def isolated_view(self, tenant_id: str, payload_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [row for row in payload_rows if row.get("tenant_id") == tenant_id]

    def stats(self) -> dict[str, int]:
        return {
            "tenants": len(self._tenants),
            "orgs": len(self._orgs),
            "memberships": sum(len(v) for v in self._memberships.values()),
            "context_profiles": len(self._context_profiles),
        }


def run_alternate_vertical_smoke_pack() -> dict[str, Any]:
    kernel = GovernanceKernel()
    kernel.register_tenant(KernelTenant("hosp-001", "health", "Mercy Clinic"))
    kernel.register_tenant(KernelTenant("gov-001", "government", "Greater LGA"))
    kernel.register_org(KernelOrg("hosp-net", "health", "Mercy Network"))
    kernel.register_org(KernelOrg("gov-net", "government", "State Education Dept"))
    kernel.link("hosp-001", "hosp-net")
    kernel.link("gov-001", "gov-net")
    rows = [
        {"tenant_id": "hosp-001", "payload": "patient-1"},
        {"tenant_id": "gov-001", "payload": "school-1"},
    ]
    isolated = kernel.isolated_view("hosp-001", rows)
    return {"isolated_count": len(isolated), "stats": kernel.stats()}


def runtime_health() -> dict[str, Any]:
    try:
        result = run_alternate_vertical_smoke_pack()
        healthy = result["isolated_count"] == 1 and result["stats"]["tenants"] == 2
        return {"contract_id": CONTRACT_ID, "healthy": healthy, "smoke_result": result}
    except CrossVerticalKernelError as exc:
        return {"contract_id": CONTRACT_ID, "healthy": False, "error": str(exc)}


def scaffold_present() -> dict[str, object]:
    h = runtime_health()
    return {"contract_id": CONTRACT_ID, "contract_title": CONTRACT_TITLE, "runtime_implementation_status": "production" if h.get("healthy") else "scaffold_only", "runtime_health": h}
