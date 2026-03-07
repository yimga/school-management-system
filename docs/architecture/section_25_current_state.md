# Section 25 — Entitlements, Observability, Security, Governance, A11y (Current State)

Phase 6 verification and scoping. 25.3 (Isolation hardening) is already done.

---

## 25.1 — Entitlements/billing

| Requirement | Current state | Notes |
|-------------|----------------|--------|
| can(tenant, "MODULE_X") | **Done** | `apps.schools.models.can(school, capability)` — alias for `is_feature_enabled(school, capability)`. Use for entitlement checks. |
| limits(tenant) | **Done** | `apps.schools.models.limits(school)` — returns dict of limit_type → limit_value from `TenantQuotaLimit`. Plan-level limits can be merged by callers. |
| Proration; usage-based billing | **Scoped** | `TenantApiUsage` model exists for API usage; proration and usage-based billing logic scoped for billing module. |
| Invoice immutability | **Scoped** | Finance module; implement when invoice lifecycle is finalized. |
| Tax engine | **Scoped** | Per-region tax (e.g. VAT/GST) scoped for finance/billing. |

---

## 25.2 — Marketplace governance

| Requirement | Current state | Notes |
|-------------|----------------|--------|
| App review pipeline | **Partial** | Marketplace app models exist; review pipeline (approve/reject) can be added to control plane. |
| Permission scopes | **Partial** | App installation and scopes in marketplace; document in app manifest. |
| Data access logs | **Done** | `AppAuditLog` in marketplace.services for install/uninstall/access events. |
| Sandbox (iframe/CSP) | **Scoped** | CSP and iframe sandbox for embedded apps; configure per deployment. |
| Versioning/compatibility | **Scoped** | App version and compatibility matrix in marketplace model/docs. |
| Revenue share/payouts | **Scoped** | Billing integration for marketplace revenue. |
| Kill switch | **Partial** | App deactivation / uninstall; global kill switch can use feature flag or app.enabled. |

---

## 25.3 — Isolation hardening

**Done.** See checklist: media tenant-prefixed; search tenant-scoped; cache keys; async/analytics tenant context. `media_tenant_scope.md`.

---

## 25.4 — Observability/SRE

| Requirement | Current state | Notes |
|-------------|----------------|--------|
| Structured logging (correlation IDs, tenant_id) | **Done** | `RequestIdLoggingMiddleware` + `RequestContextFilter` (apps.observability): request_id, tenant_id, user_id on every log line; X-Request-ID on response. LOGGING formatter uses request_context filter. |
| Metrics | **Scoped** | Prometheus/StatsD metrics and dashboards; implement with observability stack. |
| Tracing (OpenTelemetry) | **Scoped** | Distributed tracing; integrate when observability stack is chosen. |
| SLOs/error budgets | **Scoped** | Define SLOs and error budgets per service; runbooks reference. |
| Runbooks | **Done** | `docs/architecture/control_plane_runbooks.md` — access, approve school, create school, switch to tenant, sync repair. |
| Synthetic monitoring | **Scoped** | Health endpoints exist (/health, /ready); synthetic checks can be added. |

---

## 25.5 — Security baseline

| Requirement | Current state | Notes |
|-------------|----------------|--------|
| WebAuthn/MFA for privileged roles | **Done** | SiteSettings `require_mfa_roles`, `require_mfa_all_staff`; `RequireMFAMiddleware`; django_otp (TOTP). WebAuthn/passkeys can be added alongside TOTP. |
| Session management | **Done** | Django session; secure cookies; session timeout configurable. |
| Rate limiting per tenant/IP/user | **Done** | `SuperAdminRateLimitMiddleware` (120/min for /super/); `throttle_tenant_request`, `throttle_ip_request` in API; AI copilot rate limit. |
| Secrets hygiene | **Scoped** | Use env/secrets manager; no secrets in code (document in security runbook). |
| SAST/DAST | **Scoped** | CI pipeline and security scanning; document in dev docs. |
| Audit logs append-only, queryable, exportable | **Done** | `AuditLog` (compliance.models_audit) — create-only from app; queryable via admin/API; export can be added (admin action or API). |

---

## 25.6 — Data governance

| Requirement | Current state | Notes |
|-------------|----------------|--------|
| Data classification | **Partial** | AuditLog has sensitivity (LOW/MEDIUM/HIGH/CRITICAL); extend to PII classification if needed. |
| Retention per region | **Scoped** | Per-region retention policies (e.g. GDPR 30 days); implement in compliance module. |
| Consent registry | **Scoped** | Consent storage and withdrawal; link to compliance/GDPR. |
| Right-to-access/export and right-to-erasure | **Scoped** | Export and erasure workflows; compliance module. |
| Data residency | **Scoped** | Tenant/schema placement and storage region; document in tenancy and compliance. |

---

## 25.7 — Accessibility/localization

| Requirement | Current state | Notes |
|-------------|----------------|--------|
| WCAG 2.2 AA | **Scoped** | Target WCAG 2.2 AA; audit templates and components; document in a11y doc. |
| RTL | **Partial** | Policy and region support `rtl`; context processor and templates can use `global_env.rtl`. |
| Pluralization, date/time, calendars | **Partial** | Django i18n; policy `default_language`; calendar/date from region and policy. |
| Terminology from Blueprint | **Done** | `global_env.terminology` and policy; no hardcoded labels in tenant UX. |
| Low-bandwidth, offline-first | **Partial** | Offline capability in policy (`offline_mode`); low-bandwidth optimizations scoped. |

---

## References

- `apps.schools.models`: `can(school, capability)`, `limits(school)`, `is_feature_enabled(school, code)`
- `apps.compliance.models_audit`: `AuditLog`
- `apps.schools.control_plane`: `log_control_plane_action`, rate_limit_super
- `docs/architecture/control_plane_runbooks.md`
- `docs/architecture/media_tenant_scope.md`
