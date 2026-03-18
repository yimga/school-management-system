# North star — Trust, compliance, and operational excellence

**Purpose:** Single reference for North star items N11–N16, N24–N26. Execution and status stay in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md); this doc is the implementation and runbook anchor.

## Trust center and compliance (N13–N16)

- **Trust center:** `super:trust_center` → `/super/trust/`. Security, compliance, data handling, retention, breach response. Keep copy and links current; audit periodically.
- **Compliance overview:** `super:compliance_overview`. Link from trust center and nav.
- **Data residency (N14):** Document in trust center and tenant config where data lives; region-specific compliance (GDPR, FERPA) in REGIONAL_POLICY_PACKS and compliance docs.
- **Audit (N15):** Sensitive actions logged; audit export at `/super/trust/` (audit export); retention and access controls in compliance docs.
- **Certifications (N16):** SOC 2 / ISO roadmap and trust signals for marketplace; document in trust center when available.

## Uptime and resilience (N11)

- **SLO/SLA:** Target uptime 99.9%; document in trust center (SLO & uptime card) and ops runbook; health checks at `/health/`, `/healthz/`.
- **Runbooks:** Common incidents and escalation; "another Bromcom-style outage" designed against (redundancy, health, observability). **Index:** [RUNBOOKS_INDEX.md](RUNBOOKS_INDEX.md).
- **References:** `scripts/phase_h_audit.py`, observability app, control plane Pulse.

## Graceful degradation (N12)

- **Rate limits:** Apply rate limits on critical APIs (e.g. auth, audit export, create-school); return **429 Too Many Requests** with `Retry-After` or a JSON body `{"error": "rate_limit", "retry_after_seconds": N}` so clients can implement "try again" flows.
- **Try again:** No silent failures or white screens under load; user-facing "Try again" or "Service busy" messaging when rate-limited or degraded.
- **Queue depth and timeouts:** Document for async jobs (Celery, outbox); user-facing messaging when services are degraded. See RUNBOOKS_INDEX and observability app.

## Observability and runbooks (N24)

- Metrics, traces, logs: observability app and platform runtime; structured logging.
- Runbooks for common incidents; on-call and escalation path in ops docs.

## Rollout and migration playbooks (N25)

- Documented migration, validation, rollback, phased rollout; no go-live disasters (§0.4.3).
- **References:** [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md), RUNBOOK_ADMIN_TO_SUPER_MIGRATION.md, launch_studio_checklist.md. Runbooks index: [RUNBOOKS_INDEX.md](RUNBOOKS_INDEX.md).
- **Migration safety:** Validate migration in sandbox; rollback path per migration run; phased rollout (no big-bang). See super:migration_cloud and super:migration_rollback.

## Support and onboarding as product (N26)

- Training and post-go-live support; "day two" experience; guided onboarding and Setup Studio as proven path.
- **References:** Phase I.5 guided onboarding, siteconfig guided_onboarding, first-run tours.
