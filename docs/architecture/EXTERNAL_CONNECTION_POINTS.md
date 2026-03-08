# External connection points — our part done, connect when ready

**Purpose:** All items that depend on external systems or product prioritisation have a clear "our part" implemented. When the external dependency or product decision is ready, connect at the points below.

**Reference:** SCOPED_WORK_VERIFICATION §3; PLATFORM_ROADMAP_5Y; REFINEMENT Priority 3–4.

---

## 1. Ed-Fi (18.1, 31.2)

| Our part | Where | Connect when |
|----------|--------|----------------|
| Mapping layer | `apps/interop/edfi/adapter.py` — `student_to_edfi`, `student_school_association_to_edfi`, `evaluation_to_edfi_grade` | External Ed-Fi API or SIS demands Ed-Fi interchange |
| Data API | `apps/api/edfi_views.py` — GET students, studentSchoolAssociations, grades (school-scoped, auth) | Point external consumer at these URLs |
| Readiness | GET `api/interop/edfi/` — returns `endpoints` and status | Use to discover base URLs and confirm implemented |

**Connection:** External system calls `api/interop/edfi/` for discovery; then GET `api/interop/edfi/students/` (and associations, grades) with school context (tenant domain or `school_slug` / `X-School-Slug`).

---

## 2. CEDS (18.2 — US reporting)

| Our part | Where | Connect when |
|----------|--------|----------------|
| Mapping layer | `apps/interop/ceds/adapter.py` — `student_to_ceds`, `enrollment_to_ceds`, `grade_to_ceds` | US reporting or state agency requires CEDS |
| Data API | `apps/api/ceds_views.py` — GET students, enrollments, grades | Point reporting pipeline at these URLs |
| Readiness | GET `api/interop/ceds/` — returns endpoints and status | Use for discovery |

**Connection:** Reporting pipeline or state agency calls `api/interop/ceds/` then GET students/enrollments/grades with school context.

---

## 3. WebAuthn / Passkeys (29.1)

| Our part | Where | Connect when |
|----------|--------|----------------|
| Registration | `apps/accounts/views_passkey.py` — passkey_registration_options, passkey_registration_verify | Already usable; client calls these to add passkey |
| Authentication | passkey_authentication_options, passkey_authentication_verify; sets `mfa_verified` | Already usable; use instead of TOTP when client supports |
| MFA verify page | passkey_verify_page; template offers passkey or TOTP | Already wired |

**Connection:** Front-end uses existing passkey endpoints; no external dependency — ready to use. When browser/device support is standard, promote passkey as primary MFA.

---

## 4. Offline / sync (16.5)

| Our part | Where | Connect when |
|----------|--------|----------------|
| Queue model | `apps/api/mobile_api.OfflineSyncQueue` — tenant-scoped queue for offline writes | Client already can POST to sync endpoints |
| Replay batch | POST `api/offline/replay_batch/` — apply batch of queued writes | Service worker or client sends queued payloads when back online |
| Delta sync | `api/offline/delta/` — DeltaSyncAPI | Client uses for incremental sync |
| Queue metrics | GET `api/offline/queue_metrics/` | Monitor queue depth |

**Connection:** Client (PWA/service worker) uses tenant-scoped IndexedDB key (e.g. `sync_queue_${school_id}`), queues writes when offline, and on reconnect POSTs to `api/offline/replay_batch/`. See `apps/api/sync_services.py` and `apps/api/sync_delta_api.py` for semantics.

---

## 5. Government / EMIS (14.5)

| Our part | Where | Connect when |
|----------|--------|----------------|
| EMIS submission model | `apps/reports.models.EMISSubmission` — school, period, status, file_path | External agency accepts report upload or API |
| Prepare/submit API | POST `api/v1/reports/emis/prepare`, POST `api/v1/reports/emis/<id>/submit` | Wire to agency portal or API when spec is available |
| Aggregates (no PII) | GET `api/government/aggregates/` — GovernmentAggregatesAPI | Permission-gated; returns counts by region |

**Connection:** When government provides submission endpoint or format: (1) extend EMISSubmission with agency_ref or external_id; (2) in submit view, call external API or upload file; (3) keep prepare flow as-is for generating the report file.

---

## 6. Commercial platform (29.10)

| Our part | Where | Connect when |
|----------|--------|----------------|
| Trials | `School.trial_end_date`; `TenantSubscription.trial_end_date`, status TRIALING | Already used; extend with trial limits if needed |
| Quote model | `apps/billing.models.Quote` — school, plan, amount, status (DRAFT/SENT/ACCEPTED) | Already present |
| Quote → subscription hook | `apps/billing.services.convert_quote_to_subscription(quote_id)` | Implement body when sign/contract flow is ready: create BillingAccount, TenantSubscription from quote |
| Self-serve / stub API | GET `api/roadmap/commercial/` (CommercialSelfServeAPI), `api/roadmap/quote-to-contract/` (QuoteToContractStubAPI) | Document for product |

**Connection:** When quote-to-contract or partner tooling is prioritised: (1) implement `convert_quote_to_subscription(quote_id)` to create subscription and set quote to ACCEPTED; (2) add POST endpoint that accepts signed quote and calls this; (3) optionally add trial signup flow that creates Quote then converts on acceptance.

---

## Summary

- **Ed-Fi, CEDS:** Adapters and data APIs implemented; use readiness URLs to discover; connect external consumer or reporting pipeline when needed.
- **WebAuthn:** Implemented; connect front-end to existing passkey views when promoting passkey as MFA.
- **Offline:** Queue and replay/delta APIs implemented; connect client (service worker) to replay_batch and delta when building offline UI.
- **EMIS:** Prepare/submit and aggregates implemented; connect submit step to government API or portal when spec is available.
- **Commercial:** Quote and trial fields exist; implement `convert_quote_to_subscription` and optional POST when product prioritises quote-to-contract.
