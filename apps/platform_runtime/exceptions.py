"""
Platform runtime and metadata-driven exception taxonomy.

Use these instead of broad `except Exception` in tenant-facing and platform
resolution paths. Supports observability, structured logging, and user-safe
messages. See plan: Workstream A3, Metadata Codex §13.
"""


class PlatformRuntimeError(Exception):
    """Base for platform/runtime resolution and metadata-driven errors."""

    pass


class RuntimeResolutionError(PlatformRuntimeError):
    """Tenant runtime could not be built or resolved (e.g. missing school, invalid blueprint)."""

    pass


class BlueprintCompatibilityError(PlatformRuntimeError):
    """Blueprint is incompatible with tenant (plan, region, or dependency)."""

    pass


class PolicyApplicationError(PlatformRuntimeError):
    """Policy bundle could not be applied or resolved."""

    pass


class MarketplaceInstallError(PlatformRuntimeError):
    """Marketplace app or pack install failed (scope, compatibility, or governance)."""

    pass


class MigrationValidationError(PlatformRuntimeError):
    """Migration profile validation or replay failed."""

    pass


class BrandImportError(PlatformRuntimeError):
    """Brand/theme import from URL or asset failed."""

    pass


class WorkflowSimulationError(PlatformRuntimeError):
    """Workflow pack simulation or replay failed."""

    pass


class DashboardAssignmentError(PlatformRuntimeError):
    """Dashboard pack assignment or resolution failed."""

    pass
