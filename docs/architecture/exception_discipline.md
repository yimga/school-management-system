# Exception discipline

**Purpose:** Replace broad `except Exception` in sensitive flows with typed, domain-specific exceptions; add structured logging (request, tenant, actor, operation). CI fails on new broad exception swallowing in sensitive areas when `CODEX_STRICT=1` (lint_broad_except --strict).

## Domain exception classes (existing)

- **apps.platform_runtime.exceptions:** `PlatformRuntimeError`, `RuntimeResolutionError`, `BlueprintCompatibilityError`, `PolicyApplicationError`, `MarketplaceInstallError`, `MigrationValidationError`, `BrandImportError`, `WorkflowSimulationError`, `DashboardAssignmentError`. Use these in runtime, policy, marketplace, and metadata paths.
- **Future:** Add domain exceptions per bounded context (e.g. finance.PaymentValidationError, people.AdmissionNumberError) where business logic raises; catch and log with tenant/actor context.

## Inventory

- **Script:** `scripts/lint_broad_except.py` reports all `except Exception` and `except BaseException` in apps/. Run with `--strict` to fail CI (or set CODEX_STRICT=1 in pre_deploy_gate).
- **Sensitive paths:** Privileged or data-sensitive code (auth, payments, migration, policy apply, tenant provisioning) must use typed exceptions and structured logging; avoid bare `except Exception` that swallows unexpected errors.

## Rules

1. Use domain-specific exception classes in new code for resolution, policy, marketplace, migration, and tenant-facing services.
2. Add structured logging with request_id, tenant_id/school_id, actor, and operation when catching in sensitive paths.
3. Fail loudly for unexpected errors in privileged or data-sensitive paths (re-raise or log and re-raise).
4. CI: When CODEX_STRICT=1, lint_broad_except --strict runs in pre_deploy_gate and fails on any broad except in apps/.
