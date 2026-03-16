# Edge-case and failure strategy

**Purpose:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §10.5.1. The platform must survive partial failures, conflicting overrides, policy collisions, workflow deadlocks, duplicate identities, bad imports, soft-deleted records, tenant over-limit, broken integrations, expired credentials, school shutdown/merger, and academic-year rollover failures.

**Authority:** This doc is the formal strategy; implement detection/mitigation in code and runbooks. Completion gate: strategy doc exists; at least detection or mitigation for each category is defined and implemented for critical flows.

---

## 1. Partial failure (service/DB/queue down)

| Aspect | Definition |
|--------|------------|
| **Behavior** | Degrade gracefully: read-only or cached data where possible; queue work for retry; return 503/retry-after for non-critical writes; never corrupt tenant data. Critical paths (auth, runtime resolution, billing webhooks) must have explicit fallback or fail-closed. |
| **Detection** | Health checks (DB, cache, queue, external APIs); structured logging with `log_exception_with_context`; metrics/alerting on error rate and latency; runbooks for each dependency. |
| **Mitigation** | Retry with backoff for transient failures; circuit breaker for external services; fallback to platform defaults when runtime/DB unavailable (per runtime_precedence); document in control-plane runbooks. |
| **Critical paths** | `get_effective_site_settings` (runtime); auth/session; payment webhooks; package apply/rollback. |

---

## 2. Conflicting overrides (runtime/precedent clash)

| Aspect | Definition |
|--------|------------|
| **Behavior** | Apply explicit precedence (platform default → regional → blueprint → policy → entitlement → tenant → sandbox). When multiple sources conflict, the higher-precedence source wins; log the resolution for audit. |
| **Detection** | Runtime inspector and precedence tests; audit log when override is applied; dashboard or API to show effective value and source. |
| **Mitigation** | Document precedence in [runtime_precedence.md](runtime_precedence.md); enforce in `get_effective_site_settings` and resolvers; no silent overwrite of higher by lower precedence. |

---

## 3. Policy collision (multiple policies apply; precedence)

| Aspect | Definition |
|--------|------------|
| **Behavior** | Policy engine must define merge/override order (e.g. platform policy < plan policy < tenant policy). Deny wins over allow when in doubt (fail closed). |
| **Detection** | Policy evaluation logs; conflict report in control plane when two policies apply to same scope with different outcomes. |
| **Mitigation** | Document policy precedence in policy bundle docs; implement deterministic resolution; expose “why this outcome” in UI. |

---

## 4. Workflow deadlock (steps waiting on each other)

| Aspect | Definition |
|--------|------------|
| **Behavior** | Workflow engine must detect cycles and waiting states; timeout long-running steps; allow operator to cancel or force-complete with audit. |
| **Detection** | Workflow state graph; detection of cycles and stuck instances; alerts when SLA exceeded. |
| **Mitigation** | Timeouts and retry limits; deadlock detection in workflow runner; manual intervention path with audit log; document in workflow runbook. |

---

## 5. Duplicate identity (same person/entity twice)

| Aspect | Definition |
|--------|------------|
| **Behavior** | Single canonical record per natural person/entity; merge flow with conflict resolution; no duplicate primary keys or unique constraints violated. |
| **Detection** | Duplicate detection jobs (email, external_id, name+DOB within tenant); integrity checks; alerts on duplicate candidates. |
| **Mitigation** | Merge tool and merge audit log; prevent duplicate creation via validation; 360 / people graph as canonical source. |

---

## 6. Bad import (malformed data, schema mismatch)

| Aspect | Definition |
|--------|------------|
| **Behavior** | Reject invalid rows; partial import with error report; no silent truncation or wrong-field mapping; dry-run option. |
| **Detection** | Schema validation before apply; row-level error collection; import job status and error file. |
| **Mitigation** | Validation layer and clear error messages; rollback or skip bad rows per config; document import format and required fields. |

---

## 7. Soft-deleted record (access after delete; referential integrity)

| Aspect | Definition |
|--------|------------|
| **Behavior** | Queries must filter out soft-deleted by default; referential integrity (FK) either use soft-delete-aware constraints or nullable FK with cleanup job. |
| **Detection** | Audit when soft-deleted record is accessed; integrity job to find orphaned references. |
| **Mitigation** | Consistent `is_active`/`deleted_at` filter in managers; restore flow with audit; cascade rules documented. |

---

## 8. Tenant over-limit (seats, storage, API rate)

| Aspect | Definition |
|--------|------------|
| **Behavior** | Enforce limits at point of use; return 402 or clear error when over limit; no silent failure or data loss. |
| **Detection** | Usage metrics per tenant; limit checks before expensive operations; alerts when approaching limit. |
| **Mitigation** | Per-plan limits in entitlement; upgrade path or grace period; document in plan/entitlement model. |

---

## 9. Broken integration (external API/connector down or invalid)

| Aspect | Definition |
|--------|------------|
| **Behavior** | Degrade: show “integration unavailable”; queue sync for retry; do not block core flows on optional integrations. |
| **Detection** | Connector health checks; last_success_at / last_error in integration config; alerts on repeated failure. |
| **Mitigation** | Retry with backoff; circuit breaker; “Reconnect” or “Refresh” in UI; document in interop runbook. |

---

## 10. Expired credentials (API keys, tokens, certs)

| Aspect | Definition |
|--------|------------|
| **Behavior** | Fail the request with clear “credential expired” message; do not retry indefinitely; prompt for renewal in UI. |
| **Detection** | Check expiry before use where possible; log 401/403 from provider; credential expiry field in config. |
| **Mitigation** | Renewal flow in control plane; alerts before expiry; document in security/trust runbook. |

---

## 11. School shutdown/merger (data retention, access, migration)

| Aspect | Definition |
|--------|------------|
| **Behavior** | Shutdown: read-only or no access per policy; data retention per legal requirement; merger: defined migration path and cutover. |
| **Detection** | Tenant lifecycle state (active, suspended, winding_down, merged); access control tied to state. |
| **Mitigation** | Runbooks for shutdown and merger; export/archive before deletion; audit all access during wind-down. |

---

## 12. Academic-year rollover failure (rollover job fails; partial state)

| Aspect | Definition |
|--------|------------|
| **Behavior** | Rollover must be transactional or clearly phased; on failure, leave system in known state (previous year still valid); no half-rolled data. |
| **Detection** | Rollover job status and logs; consistency checks (e.g. current year matches expected); alerts on failure. |
| **Mitigation** | Idempotent or two-phase rollover; rollback path; document in academic runbook; dry-run option. |

---

## Implementation status (critical paths)

| Category | Detection implemented | Mitigation implemented | Notes |
|----------|------------------------|-------------------------|------|
| 1. Partial failure | Health checks, logging | Runtime fallback, retries | get_effective_site_settings fallback; Billing/Finance webhooks 401 on invalid. |
| 2. Conflicting overrides | Runtime inspector, precedence tests | runtime_precedence.md + resolver | get_effective_site_settings precedence. |
| 3. Policy collision | — | Policy precedence doc | Implement conflict report in control plane when needed. |
| 4. Workflow deadlock | — | — | Add timeout and deadlock detection in workflow runner. |
| 5. Duplicate identity | — | — | Merge flow and duplicate detection per product. |
| 6. Bad import | Validation in importers | Error report, dry-run | Per-importer; standardize pattern. |
| 7. Soft-deleted record | Manager filters | — | Consistent filter in managers; restore flow. |
| 8. Tenant over-limit | — | Entitlement checks | Add usage checks at point of use. |
| 9. Broken integration | Connector health | Retry, circuit breaker | Per connector; interop runbook. |
| 10. Expired credentials | — | Renewal flow | Trust product surfaces. |
| 11. School shutdown/merger | Tenant lifecycle state | Runbooks | control_plane_lifecycle; wind-down runbook. |
| 12. Academic-year rollover | — | Transactional or phased rollover | Rollover job design. |

*Update this table as detection/mitigation is implemented. Completion gate: at least detection or mitigation for each category defined and implemented for critical flows.*
