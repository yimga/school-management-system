"""
Platform runtime: unified TenantRuntime per request.
Single entry point for tenant identity + policy + workflow/dashboard resolution.
"""

from .contracts import TenantRuntime
from .exceptions import (
    BlueprintCompatibilityError,
    BrandImportError,
    DashboardAssignmentError,
    MarketplaceInstallError,
    MigrationValidationError,
    PlatformRuntimeError,
    PolicyApplicationError,
    RuntimeResolutionError,
    WorkflowSimulationError,
)
from .runtime_resolver import build_tenant_runtime

__all__ = [
    "TenantRuntime",
    "build_tenant_runtime",
    "PlatformRuntimeError",
    "RuntimeResolutionError",
    "BlueprintCompatibilityError",
    "PolicyApplicationError",
    "MarketplaceInstallError",
    "MigrationValidationError",
    "BrandImportError",
    "WorkflowSimulationError",
    "DashboardAssignmentError",
]
