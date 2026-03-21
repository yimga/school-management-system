# Platform boundary: operator (manager) vs tenant

**Status:** Canonical product/security contract for RunMyCampus. Implementation references: `apps/schools/control_plane.py`, `apps/accounts/middleware.py`, `config/manager_urls.py`, `config/tenant_urls.py`.

## Two products, shared libraries

| Plane | Host | Purpose |
|--------|------|---------|
| **Operator** | `manager.<base>` | Fleet governance, provisioning, billing, support, security — **not** day-to-day school operations. |
| **Tenant** | School subdomain / custom domain | Everything school-scoped: the real product for that school. |
| **Bridge** | Signed impersonation | When an operator must see tenant truth, they use **Open as school** (audited, time-boxed token, optional read-only). |

## Non-negotiable rules

1. **Routing:** Tenant-primary paths must not behave as school workflows on the manager host. Today: `/studio/hubs/workflow/`, `/studio/hubs/approvals/`, `/studio/hubs/import/`, and `/authentication/backend/` are **blocked** on the manager host (`ManagerTenantPrimarySurfaceBlockMiddleware`, alias `ManagerTenantPrimaryStudioHubBlockMiddleware`) and guarded in views (`apps/accounts/views_workflow.py`, `backend_dashboard` in `apps/accounts/views.py`). **Ordering:** `ReservedPublicHostAccessMiddleware` only allows known manager paths (`MANAGER_HOST_ALLOWED_PREFIXES` in `apps/schools/middleware.py`); tenant-primary URLs like `/authentication/backend/` must appear there so requests are not short-circuited with `HttpResponseRedirect("/")` before the block middleware runs.
2. **Context:** School-shaped logic requires `request.school` / correct schema on the tenant host.
3. **Authorization:** Manager host authenticated surfaces (outside public/bootstrap paths) require **control-plane** access (`user_has_control_plane_access`: superuser or `SUPERADMIN`), not generic `is_staff`. Studio OS on the manager host uses `user_can_access_studio_on_request()` (`apps/schools/control_plane.py`); tenant Studio remains staff-gated.

## Impersonation

- **Justification:** When `IMPERSONATION_REQUIRE_JUSTIFICATION` is enabled (default in `config/settings.py`), `switch_to_tenant` requires `impersonation_reason` (min 3 characters). Optional `support_ticket_ref`; `ImpersonationLog` stores reason, ticket ref, and `read_only`.
- **TTL:** `IMPERSONATION_TOKEN_MAX_AGE_SECONDS` applies to signed tokens (see `apps/accounts/views_impersonation.py`).
- **Read-only:** Default is read-only unless the operator checks **Allow write actions**. When `read_only` is set on the session, `ImpersonationReadOnlyGuardMiddleware` blocks unsafe HTTP methods on configured prefixes (admin, API, finance, portal, studio, etc.). Adjust `IMPERSONATION_READ_ONLY_BLOCKED_WRITE_PREFIXES` for your posture.

## Verification

- Automated: `apps/schools/tests/test_manager_studio_tenant_boundary.py`, `apps/accounts/tests/test_tenant_host_control_plane_isolation.py`, `apps/schools/tests/test_world_engine_switch_tenant_consent.py`.
- Manual: staging that mirrors production hostnames; confirm manager bookmarks to tenant hubs redirect to `/super/`.

## DR, backups, and workers (reminder)

- **Backups** must include **all tenant schemas** (schema-per-tenant); restore drills should prove RTO/RPO with a written record — see [DR_BACKUP_RESTORE_RUNBOOK.md](DR_BACKUP_RESTORE_RUNBOOK.md).
- **Workers / cron / management commands** must set **tenant/schema context** explicitly; a mistaken default connection is a classic cross-tenant corruption vector. Track fixes in the single execution source of truth, not parallel plans.

## Related docs

- [THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md](THREAT_MODEL_AI_WEBHOOKS_EXPORTS.md) — high-level threats for AI, webhooks, uploads, exports.
- [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) — execution ledger (single source of truth).
