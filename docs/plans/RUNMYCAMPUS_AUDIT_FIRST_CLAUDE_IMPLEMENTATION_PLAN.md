# RunMyCampus Audit-First Claude Implementation Plan

## Purpose

This plan is for Claude or another implementation agent. The goal is to implement the audit-first direction without replacing existing RunMyCampus architecture.

The first deliverable is not product-code replacement. The first deliverable is a file-backed truth layer that proves what exists, what is unproven, what is external-blocked, and what should be retained, adapted, deferred, rejected, or implemented.

## Non-Negotiable Guardrails

- Do not replace tenant context, `request.school`, tenant middleware, schema-per-tenant mode, RLS mode, tenant-aware task context, or control-plane versus tenant-plane boundaries.
- Do not replace the offline architecture. Preserve both `OfflineAction` typed intents and IndexedDB/WAL stream behavior.
- Do not create a second AI gateway. Keep external AI, local AI, budgets, PII controls, and fallbacks behind the existing AI gateway boundaries.
- Do not hardwire the platform to Stripe, Twilio, Sentry, Anthropic, Cloudflare, AWS, Kubernetes, Kafka, Temporal, OpenSearch, ClickHouse, Ceph, Qdrant, or vLLM.
- Do not claim production readiness from documentation or local SQLite checks alone.
- Do not declare external items complete unless credentials, accounts, legal approval, live vendor configuration, or operator review actually exists.

## Implementation Deliverables

Create or update these files:

1. `docs/generated/sovereign_tenant_repo_snapshot.json`
2. `docs/generated/sovereign_tenant_repo_snapshot.md`
3. `docs/generated/runmycampus_forensic_capability_matrix.json`
4. `docs/generated/runmycampus_forensic_capability_matrix.md`
5. `docs/generated/runmycampus_vendor_and_infrastructure_decision_matrix.md`
6. `docs/plans/runmycampus_reality_based_gap_closure_plan.md`

The generated files must be based on current source code, current docs, and command output. Do not fill them with unsupported claims.

## Step 1: Repository Truth Snapshot

Inspect the active repo at:

```text
beta/school-management-system
```

Capture:

- current branch;
- `git status --short`;
- `git diff --stat`;
- app/module count;
- migration count;
- test file count;
- template/static counts;
- deployment files and profiles;
- middleware and tenant-related modules;
- offline, sync, WAL, CRDT, and service-worker modules;
- AI gateway/provider modules;
- billing/payment/provider modules;
- communications provider modules;
- observability and Sentry modules;
- backup, restore, offboarding, and data export modules;
- existing verification and scanner scripts.

Write this to:

- `docs/generated/sovereign_tenant_repo_snapshot.json`
- `docs/generated/sovereign_tenant_repo_snapshot.md`

## Step 2: Capability Matrix

For each capability, classify status as exactly one of:

```text
MISSING
PARTIAL
FUNCTIONAL
FUNCTIONAL_BUT_FRAGMENTED
FUNCTIONAL_BUT_UNPROVEN
UNSAFE
EXTERNAL_BLOCKED
```

Capabilities to score:

- tenant ingress and host routing;
- tenant context and middleware;
- PostgreSQL RLS/JWT tenant binding;
- tenant-aware async tasks;
- cache and file tenant boundaries;
- offline authentication and device registration;
- MFA and offline authorization;
- `OfflineAction` typed-intent rail;
- IndexedDB/WAL stream rail;
- CRDT/conflict policy;
- seven-day offline survival proof;
- country metadata and optional identifiers;
- grading/report-card engine;
- academic-year close;
- finance immutability and ledger behavior;
- PPP and economic localization;
- Stripe/PSP provider boundary;
- billing entitlements;
- communications/email/SMS provider boundary;
- object storage and secure documents;
- data residency and border lock;
- backup/restore/offboarding/purge;
- AI gateway and provider boundaries;
- RAG/vector store boundary;
- tenant UX shell and accessibility;
- observability, Sentry, OpenTelemetry, health checks;
- deployment readiness;
- SDK/public API readiness;
- marketplace governance;
- pilot/customer onboarding tooling;
- external owner-controlled launch work.

For each capability include:

- canonical owner files;
- consumers;
- tests or proof found;
- tenant impact;
- offline/local-first impact;
- security/privacy impact;
- gaps;
- recommended remediation: `retain`, `repair`, `consolidate`, `deprecate`, `replace`, `test only`, or `external proof required`.

Write this to:

- `docs/generated/runmycampus_forensic_capability_matrix.json`
- `docs/generated/runmycampus_forensic_capability_matrix.md`

## Step 3: Vendor And Infrastructure Decision Matrix

Create:

```text
docs/generated/runmycampus_vendor_and_infrastructure_decision_matrix.md
```

For each listed tool or provider, make one decision:

```text
ADOPT NOW
ADAPT EXISTING
CERTIFY OPTIONAL PROFILE
DEFER UNTIL TRIGGER
REJECT
RESEARCH SPIKE ONLY
```

Cover:

- Cloudflare DNS;
- Route53/AWS DNS;
- S3-compatible storage;
- AWS S3;
- Cloudflare R2;
- Sentry;
- OpenTelemetry;
- Prometheus/Grafana;
- Stripe Billing;
- Stripe Connect;
- Twilio;
- Vonage/Africa's Talking/regional SMS;
- transactional email providers;
- Anthropic;
- OpenAI;
- Ollama;
- LiteLLM;
- PGVector;
- Qdrant/Milvus;
- Kubernetes;
- K3s;
- Docker Compose/self-host;
- CloudNativePG;
- PgBouncer;
- Redis/Valkey;
- Celery;
- Kafka/Redpanda;
- NATS;
- Temporal;
- OpenSearch;
- ClickHouse;
- Ceph;
- vLLM/KServe;
- GitOps/Argo CD;
- OpenBao/Keycloak.

Decision defaults:

- Docker/self-host/local edge: `ADAPT EXISTING`
- Cloudflare DNS: `ADOPT NOW` only for production custom-domain automation, otherwise external-blocked
- Sentry: `ADAPT EXISTING`
- OpenTelemetry: `ADOPT NOW` only as vendor-neutral instrumentation, not a replacement
- Kubernetes/K3s: `CERTIFY OPTIONAL PROFILE`
- Kafka, Temporal, OpenSearch, ClickHouse, Ceph, Qdrant, vLLM/KServe: `DEFER UNTIL TRIGGER` unless benchmark evidence proves immediate need
- Mandatory proprietary SaaS dependency for core operation: `REJECT`

## Step 4: Gap Closure Plan

Create:

```text
docs/plans/runmycampus_reality_based_gap_closure_plan.md
```

Use this wave order:

1. Wave 0: truth reconciliation and repo snapshot.
2. Wave 1: tenant ingress, routing, RLS/JWT, async/cache tenant scope.
3. Wave 2: offline auth, MFA, device trust, revocation, logout purge.
4. Wave 3: CRDT/offline data engine and domain conflict classification.
5. Wave 4: seven-day offline survival simulation.
6. Wave 5: data residency, backup, restore, offboarding, purge proof.
7. Wave 6: country metadata, grading, academic-year closure.
8. Wave 7: finance immutability, PPP, billing, Stripe/PSP boundaries.
9. Wave 8: tenant UX, accessibility, browser proof.
10. Wave 9: observability, health, Sentry/OpenTelemetry, deployment readiness.
11. Wave 10: external-owner launch backlog.

For each wave include:

- objective;
- repo-controlled tasks;
- external-owner tasks;
- files likely involved;
- tests required;
- acceptance gate;
- claims that are not allowed until evidence exists.

## Step 5: Audit Tooling Fixes Only If Needed

If audit scripts rewrite tracked generated files by default, add explicit read-only or dry-run modes before using them in CI.

If `scripts/generate_external_dependencies_register.py` fails on Windows due to Unicode stdout encoding, fix output handling so it can print or write UTF-8 safely.

Do not refactor unrelated code while doing these fixes.

## Required Verification Commands

Run and record results in the plan or generated audit files:

```powershell
git branch --show-current
git status --short
git diff --stat
git diff --check
python manage.py check
python manage.py makemigrations --check --dry-run
python -m compileall -q apps config scripts
python scripts\verify_service_worker_version.py --check-monotonic
python scripts\verify_database_tenancy_contract.py
python scripts\scan_ai_gateway_boundary.py
python scripts\scan_sentry_boundary.py
python scripts\scan_pii_logging_smell.py
python scripts\scan_tenant_queryset_safety.py
python scripts\generate_external_dependencies_register.py
```

If any command mutates tracked files unexpectedly, stop, record it as an audit tooling defect, and restore only the files changed by that command.

## Acceptance Criteria

This implementation is complete when:

- the six deliverable files exist;
- every score or status has source evidence;
- stale generated-doc conflicts are explicitly identified;
- external-blocked items are separated from repo-controlled work;
- no replacement architecture is introduced;
- no public product API is changed;
- verification command results are recorded;
- `git status --short` shows only intentional files changed.

## First Safe Claude Prompt

Use this prompt to start implementation:

```text
Implement docs/plans/RUNMYCAMPUS_AUDIT_FIRST_CLAUDE_IMPLEMENTATION_PLAN.md exactly.

Do not replace existing RunMyCampus systems. First inspect the current repo, then create the snapshot, forensic capability matrix, vendor/infrastructure decision matrix, and reality-based gap closure plan. Fix audit tooling only if it blocks truth collection, and keep changes scoped. Record command evidence and separate repo-controlled work from external-owner work.
```
