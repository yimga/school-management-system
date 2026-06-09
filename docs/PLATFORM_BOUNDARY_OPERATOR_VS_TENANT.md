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
4. **Sign-in URLs (slug-first):** School owners and staff sign in only on **`https://{slug}.<base>/authentication/login/`** (their workspace). The marketing apex (`runmycampus.com`) is **not** a sign-in surface: `/authentication/login/` and related tenant auth paths redirect to **`/discover/`** (`APEX_TENANT_AUTH_DISCOVERY_PREFIXES` in `apps/schools/middleware.py`). Campus discovery (`/discover/`, `/find/`) hands users to the slug URL. The manager host login form is **operator-only**: unauthenticated visits to `manager.<base>/authentication/login/` redirect to discovery unless the request carries operator intent (`?next=/super/…`, `?next=/admin/…`, or `?cp=1`). After login on a tenant host, members stay on that slug; rare public-host sessions hand off via `resolve_public_post_login_handoff()` in `apps/schools/tenant_login_redirect.py`. Pending tenants (`is_active=False`) may use `/authentication/*` on their subdomain (`PENDING_TENANT_AUTH_PREFIXES`).
5. **Session cookies (production):** Set `SESSION_COOKIE_DOMAIN` and `CSRF_COOKIE_DOMAIN` to the parent domain (e.g. `.runmycampus.com` in `render.yaml`) so a rare manager→public handoff can reuse the browser session. Manager uses separate cookie names (`MANAGER_SESSION_COOKIE_NAME`) when configured.

## Operator entry (bookmarks)

| Intent | URL |
|--------|-----|
| Control plane after auth | `https://manager.runmycampus.com/super/` (redirects to login with `next=/super/…`) |
| Explicit operator login | `https://manager.runmycampus.com/authentication/login/?cp=1` |
| School owner / staff (preferred) | `https://{slug}.runmycampus.com/authentication/login/` |
| School owner / staff (discovery) | `https://runmycampus.com/discover/` or `/find/` → slug campus sign-in |

## Signup → portal (tenant)

1. Signup creates `School` with `is_active=False`.
2. Email verification on the **public** host queues or sync-runs `complete_provisioning_for_school`.
3. Owner onboarding launchpad (`/authentication/onboarding/done/`) polls `…/onboarding/done/status/` until `is_active` flips, then sends the portal-ready email.
4. Stuck slugs: `python manage.py triage_signup_school <slug>` then `activate_pending_signup_schools --slug=<slug>` when verified-but-inactive.
5. **Tenant emails:** portal-ready and win-back messages prefer `build_tenant_workspace_login_url()` / `tenant_portal_url` — never `manager.runmycampus.com` (`signup_completion_notifications.build_signup_completed_payload`, `reactivation_engine._portal_url_for_reactivation`).

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
