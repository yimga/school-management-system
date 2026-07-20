# Migration Cloud — Tenant Dominance Audit (Phase 0)

**Status:** AUDIT COMPLETE — no code changes in this artifact  
**Date:** 2026-07-20  
**Bar:** AWS (reliability) · Linux (ops honesty) · Shopify (tenant self-serve) · Salesforce (data gravity)  
**Live tenant under investigation:** `https://new-school.runmycampus.com/` (slug `new-school`)  
**Reported defect:** files uploaded; school data does not appear ingested  

**Twin:** `docs/generated/migration_cloud_tenant_dominance_audit.json`  
**SOT mapping:** recommend §11.4 burn-down rows in §9 below (do not claim DONE until Phase 1+ ships + proofs).

---

## Executive verdict

Migration Cloud has a real ingest→advance→apply spine and a credible tenant UI at  
`/school/setup/migration-cloud/`. **Upload alone never lands school rows** — that is by design.  
Two **code-proven** defects make “upload worked, school empty” the default failure mode on production tenants:

| P0 | Finding | Evidence |
|----|---------|----------|
| **P0-A** | Tenant + portal intake bind `schema_name=getattr(school, "schema_name", "")` — **School has no `schema_name` attribute**. Canonical schema lives on `customers.Client.schema_name` (`s_<uuid-hex>`). Empty `bundle.schema_name` → apply skips `schema_context` → rows land off-tenant (or nowhere the school UI reads). | `views_tenant_upload.py:331`, `views.py:359/383/1657`, `orchestrator._run_lander_under_schema` empty-schema branch, `schools/models` (no field), `tenant_offboarding.get_schema_name` (correct Client lookup unused by MC) |
| **P0-B** | Companion decrypt comments “persist plaintext as intake artifact” but **discards plaintext** after marking `INGESTING`. No `MigrationArtifact`, no advance, no apply. | `companion_receiver.py:854–888` |

Secondary but load-bearing: apply requires **MAPPED + explicit `confirm=1`**; dry-run is the default and stays at MAPPED. Domain overrides on the tenant review form write `artifact.assigned_domain` but apply routes via `discovery_summary.per_artifact_domain`, and re-`advance` is a **no-op once MAPPED**.

**Live DB forensic for `new-school`:** **BLOCKED** from this workstation (local `.env` is not Postgres production). HTTP probe confirms the tenant host is live and the MC upload path redirects to login (route exists). Operator must run shell one-liners in §2.2 on Render/prod to classify this tenant’s bundles.

---

## 0.1 Rail map (do not conflate)

| Rail | Entry (named URL / path) | Lands StudentProfile / etc.? | Notes |
|------|--------------------------|------------------------------|-------|
| **A. Tenant connectionless** | Tenant host `/school/setup/migration-cloud/` → `migration_cloud_connector:upload` → `bundle-review` → `bundle-apply` | **YES** after live apply | Primary Shopify-bar path. Mount: `config/tenant_urls.py` → `urls_connectors.py`. Views: `views_tenant_upload.py` |
| **B. Portal wizard** | `/portal/configure/migration/` (`migration_cloud_portal`) | YES if entitled + apply | `_enforce_portal_entitlement` → capability `migration_cloud` → **402** if missing. Seeded on `enterprise-network` plan |
| **C. Super/operator** | `/super/migration/` (`migration_cloud_super`) | Operator support / bind / apply | Same grammar as portal; staff gates |
| **D. Customer intake** | `/migration/` (`migration_intake_customer`) | **NO** file land by itself | `MigrationIntakeRequest` FSM + MAA + consent counters |
| **E. Companion sealed-box** | `companion_upload` / `companion_decrypt` under portal/super | **NO** today after decrypt | Creates receipt + PENDING bundle; decrypt → INGESTING **without artifacts** (**P0-B**) |
| **F. REST API v1** | `…/api/v1/bundles/` + `artifacts/bulk` + `advance` + `apply/?confirm=1` | YES if advance+apply | Bulk alone does not advance |
| **G. Connector live system** | `connector-connect` → discover → map → validate → import | YES (advance+apply in one shot when MAPPED) | Quality ≥ 70, verified connection, auth confirmed |
| **H. Legacy accounts wizard** | `accounts:migration_wizard` → `/authentication/backend/migration-wizard/` | Parallel / older path | Confusion risk; not the connectionless lander spine |

**Pipeline spine (shared):**  
`BundleIngestionService.ingest` → `advance_bundle` (profile→classify→map) → **MAPPED** → `apply_bundle` (`confirm=1`) → landers under `schema_context(bundle.schema_name)` → optional reconcile/verify.

```
PENDING → INGESTING → PROFILED → CLASSIFIED → MAPPED → APPLYING → APPLIED → RECONCILED
                                                              ↘ FAILED / ABORTED
```

---

## 0.2 Live tenant forensic — `new-school`

### 0.2.1 What we could prove remotely (no auth / no prod DB)

| Check | Result | Status |
|-------|--------|--------|
| Host resolves | `https://new-school.runmycampus.com/` → **302** → `/authentication/login/` | DONE |
| MC upload route | `…/school/setup/migration-cloud/upload/` → **302** → login with `?next=…/upload/` | DONE — route mounted |
| Manager health | `manager.runmycampus.com/super/migration/health/` timed out / auth wall | PARTIAL |
| Prod `MigrationBundle` dump | Local env has no Postgres `DATABASE_URL` | **BLOCKED (EXTERNAL)** |

### 0.2.2 Operator shell (run on production — paste results into this doc)

```python
from apps.schools.models import School
from apps.customers.models import Client
from apps.billing.entitlements import can
from apps.migration_cloud.models import (
    MigrationBundle, MigrationArtifact, CompanionUploadReceipt, MigrationProgressEvent,
)
from apps.automation.models import MigrationRun
from apps.schools.tenant_offboarding import get_schema_name

school = School.objects.filter(slug="new-school").first() or School.objects.filter(subdomain="new-school").first()
client = Client.objects.filter(school=school).first()
print({
    "school_id": str(school.pk),
    "schema_client": getattr(client, "schema_name", None),
    "schema_helper": get_schema_name(school),
    "entitled": can(school, "migration_cloud"),
})
for b in MigrationBundle.objects.filter(school=school).order_by("-created_at")[:20]:
    print(b.pk, b.status, repr(b.schema_name), b.intake_method,
          "arts=", b.artifacts.count(),
          "err=", (b.size_summary or {}).get("error"),
          "apply=", (b.mapping_summary or {}).get("apply_totals"))
print("companion", CompanionUploadReceipt.objects.filter(tenant=school).count())
print("runs", list(MigrationRun.objects.filter(school=school).order_by("-started_at")[:10].values(
    "id", "dry_run", "status", "created_count", "error_count", "error_message")))
```

### 0.2.3 Classification tree (for each bundle found)

1. `PENDING` + companion receipt, `decrypted_at is None` → waiting decrypt  
2. `INGESTING` + **0 artifacts** → **P0-B companion theater**  
3. Artifacts > 0, status &lt; `MAPPED` → advance stuck (Celery / `size_summary.error`)  
4. `MAPPED` + no live `MigrationRun` / no apply_totals → **never confirmed apply** (UX / Shopify gap)  
5. `APPLIED` + empty `schema_name` or schema ≠ Client → **P0-A invisible rows**  
6. `APPLIED` + quarantine tall → data held, not dropped  

### 0.2.4 Auth / entitlement / nav (code + HTTP)

| Item | Finding | Status |
|------|---------|--------|
| Tenant-admin gate on upload/apply | `_TenantAdminWriteRequiredMixin` / `user_is_tenant_admin` | DONE (code) |
| Portal entitlement | `migration_cloud` capability; 402 on portal shell | DONE (code) |
| Tenant connector path entitlement | **Not** portal-gated the same way — tenant `/school/setup/migration-cloud/` is the self-serve rail | DONE |
| Nav discoverability | Studio hub `school/studio/migration/` **redirects** to `school_setup_imports` (not MC upload). Onboarding catalog mentions MC upload. Risk: tenant cannot find the rail | **OPEN** |

---

## 0.3 End-to-end domain contract matrix

Canonical headers: `accelerators/runmycampus_canonical.py::DOMAIN_CANONICAL_HEADERS` (27 domains).  
Landers: `landers/*.py` (+ `academics` lander **not** in header SOT).  
Phantom-field scanner: **0** (2026-07-20).

| Domain | Lander | First-class model | Tenant UI surface (typical) | Land test coverage | Gap |
|--------|--------|-------------------|-----------------------------|--------------------|-----|
| students | `student_lander.py` | `people.StudentProfile` | Students / people lists | connectionless + lander suites | — |
| staff | `staff_lander.py` | `people.TeacherProfile` | Staff / teachers | same | — |
| guardians | `guardian_lander.py` | `people.StudentGuardian` | Parent links | same | FK order quarantine if students missing |
| enrollment | `enrollment_lander.py` | updates `StudentProfile` | Student enrollment fields | same | — |
| structure | `structure_lander.py` | AY/Term/Dept/Classroom/… | Academics setup | same | Wave 0 required |
| sections | `sections_lander.py` | `academics.Classroom` | Classes | same | — |
| attendance | `attendance_lander.py` | `academics.Attendance` | Attendance | same | — |
| grades | `grades_lander.py` | `evals.Evaluation` | Gradebook | same | — |
| behavior | `behavior_lander.py` | `academics.Incident` | Discipline | same | — |
| finance | `finance_lander.py` | `finance.Invoice` | Finance / invoices | same | Guardrail abort; repair constraints |
| transcripts | `transcripts_lander.py` | `people.TranscriptVaultItem` | Transcript vault | same | — |
| health | `health_lander.py` | `schoolops.HealthRecord` | Health | same | — |
| payroll | `payroll_lander.py` | **DFV only** (honest) | Custom fields — **not Payslip UI** | lander | Looks “empty” in Payroll UI |
| communications | `communications_lander.py` | `communication.Message` | Messages | same | — |
| events | `events_lander.py` | `school_events.SchoolEvent` | Events | same | — |
| library | `library_lander.py` | `schoolops.LibraryItem` | Library | same | — |
| transport | `transport_lander.py` | `schoolops.Route` | Transport catalog | same | — |
| hostel | `hostel_lander.py` | `schoolops.HostelRoom` | Hostel catalog | same | — |
| cafeteria | `cafeteria_lander.py` | `schoolops.CanteenMeal` | Cafeteria catalog | same | — |
| transport_assignments | `transport_assignment_lander.py` | `TransportAssignment` (+ DFV fallback) | Assignments | assignment tests | DFV if Route missing |
| hostel_assignments | `hostel_assignment_lander.py` | `HostelAssignment` (+ DFV) | Assignments | same | same |
| cafeteria_assignments | `cafeteria_assignment_lander.py` | `MealPlanBalance` (+ DFV) | Meal plans | same | same |
| alumni | `alumni_lander.py` | `StudentProfile` alumni status | Alumni / students | same | — |
| compliance | `compliance_lander.py` | **DFV only** (honest) | Custom fields — **not ComplianceCheck UI** | lander | Looks empty in Compliance |
| athletics_teams | `athletics_teams_lander.py` | `athletics.Team` | Athletics | athletics landers | — |
| athletics_memberships | `athletics_memberships_lander.py` | `TeamMembership` | Athletics roster | same | — |
| athletics_fixtures | `athletics_fixtures_lander.py` | `Fixture` (+ result) | Athletics fixtures | same | — |
| custom_fields | `dynamic_field_lander.py` | `metadata.DynamicFieldValue` | Metadata / custom | catch-all | Never drop invariant |
| academics *(lander only)* | `academics_lander.py` | `academics.Subject` | Subjects | lander | **Not** in `DOMAIN_CANONICAL_HEADERS` — tagger/templates may miss it |

**Verification honesty:** post-apply `verification.py` re-queries visible counts for **students / staff / guardians / finance** only — other domains show “—” for visible count (Salesforce bar gap).

---

## 0.4 Failure-mode catalog

| # | Mode | Status | Proof |
|---|------|--------|-------|
| 1 | Upload without confirm-apply | **CLOSED (UX)** | Banner + upload copy + success toast (P1-UX) |
| 2 | Non-admin upload/apply | **CLOSED (code)** | Admin mixin + gates green |
| 3 | Missing portal entitlement | **PARTIAL** | Portal 402 real; tenant connector rail not same gate |
| 4 | Advance stuck (Celery) | **PARTIAL** | Soft-fail → inline; still no beat auto-advance (by design) |
| 5 | Quarantined / 0-row (PDF/XLSX) | **PARTIAL** | Hints on review UI |
| 6 | Wrong domain / override ignored | **CLOSED** | P1-Override remount + `_build_jobs` honor assigned_domain |
| 7 | Empty `schema_name` | **CLOSED (code)** | P0-A resolver + apply refuse |
| 8 | Companion decrypt without ingest | **CLOSED** | P0-B ingest + advance |
| 9 | Idempotent re-upload “nothing new” | **PARTIAL** | Correct AWS behavior; UX explains reuse |
| 10 | Cross-host `{% url %}` after companion | **PARTIAL** | Pre-resolved URLs on tenant templates |
| 11 | Financial mismatch abort | **CLOSED (code)** | Guardrail + repair refusal |
| 12 | Connector quality &lt; 70 | **CLOSED (code)** | Import blocked with coded errors |
| 13 | Legacy wizard confusion | **CLOSED (UX)** | P2 deprecation banner → MC upload |
| 14 | Connector tables RLS | **PARTIAL** | Migrations 0037/0038 |
| 15 | Offline / resume mid-ingest | **DONE** | SODP + IndexedDB blobs (`enable_offline_migration_cloud_upload`); batch 1770 |

---

## 0.5 UX / Shopify bar

| Criterion | Score | Notes |
|-----------|-------|-------|
| One job / one CTA chain | PARTIAL | Upload → Review → Import exists; success copy after upload can feel like “done” |
| Dry-run vs live impossible to miss | PARTIAL | Labels are clear (“Preview” / “Import into my school”); default dry-run is correct |
| Progress honesty | PARTIAL | Poll + stage badges; 5‑min timeout message; infinite detecting still possible if advance dead |
| Empty / error next action | PARTIAL | Quarantine hints + repair panel present |
| Page-fold / pagination | PARTIAL | `data-rmc-scroll-policy="paginate"` on connector shell; large quarantine lists need ongoing proof |
| i18n | PARTIAL | Review template uses `{% trans %}`; keep auditing other MC templates |
| Feature gate vs broken empty | PARTIAL | Portal paywall; tenant rail must not 500 |

**Emotional state:** anxious admin importing a year of data needs: stage name, next button, failure reason, and “verified in your school” counts — the review template already aims there; **P0-A** breaks trust after a green Import.

---

## 0.6 Security / Salesforce data gravity

| Criterion | Status | Notes |
|-----------|--------|-------|
| RBAC on mutating routes | DONE (code) | Tenant admin / staff gates; API scoped tokens |
| Tenant queryset scope | PARTIAL | Bundle metadata shared; land under schema — **broken when schema empty** |
| No secrets in logs | DONE (gate family) | Companion logs sizes/ids not plaintext |
| Audit events | PARTIAL | Companion upload/decrypt audited; ensure advance/apply emission coverage |
| API token scopes | DONE | Scoped tokens + throttle middleware |
| CSRF on forms | DONE | Tenant review/apply forms use `{% csrf_token %}` |

---

## 0.7 Ops / AWS + Linux bar

| Item | Status |
|------|--------|
| Celery `migration_cloud.advance_bundle` / `apply_bundle` | Present; apply task defaults **dry_run=True** |
| Beat: webhook deliver, audit chain weekly, smoke nightly, token watchdog, retention | Present in `config/settings.py` |
| Beat auto-apply tenant uploads | **Absent** (correct — needs human confirm) |
| Health `/super/migration/health/` | Operator panels (webhooks, MAA, companion, scanners) |
| Repair path | `repair.repair_bundle` + tenant `bundle-repair` UI |
| Smoke | `migration_cloud_smoke --tenant=<slug>` |
| Support runbook for “upload OK, school empty” | **THIS AUDIT §2.2 + §0.4** — promote into operator docs in Phase 1 |

---

## 0.8 Proof inventory (executed 2026-07-20)

| Gate / suite | Result |
|--------------|--------|
| `scan_lander_phantom_fields.py` | **0** |
| `scan_migration_model_imports.py` | **0** |
| `scan_companion_canonical_headers_drift.py` | **0** drift |
| `verify_migration_cloud_connectors.py` | **PASS** (8) |
| `verify_migration_cloud_intake_experience.py` | **PASS** (12/12) |
| Django: `test_tenant_apply_admin_gate` + `test_apply_role_gate` + `test_tenant_progress_2026_07_13` | **21 OK** |
| Playwright `tests/e2e/migration-cloud.spec.js` | **NOT RUN** (no live authenticated sweep this session) |
| Prod DB forensic `new-school` | **BLOCKED** |

---

## 0.9 Ranked burn-down queue (Phase 1+)

Industry-leader order — implement only after this audit is accepted:

| Rank | ID | Slice | Pillar | Acceptance proof |
|------|-----|-------|--------|------------------|
| 1 | **P0-A** | Resolve schema via `Client.schema_name` / `get_schema_name(school)` at **all** intake sites (`views_tenant_upload`, `views.py`, `intake_init`, `connector_bundle_bridge`). Backfill empty `schema_name` on existing bundles for `new-school`. Refuse apply when schema missing on a bound school. | AWS + Salesforce | Unit + integration: upload on tenant host → apply → `StudentProfile` count in `schema_context`; regression test that `getattr(school,"schema_name")` path is gone |
| 2 | **P0-B** | Companion decrypt → write plaintext through `BundleIngestionService` → enqueue advance (or honest error if format unsupported). Never leave INGESTING with 0 artifacts claiming success. | AWS + Linux | Companion decrypt test asserts artifacts ≥ 1 and status progresses |
| 3 | **P1-UX** | Post-upload CTA: force review stage messaging “Not in your school yet”; disable leaving without Import or show checklist. | Shopify | Template markers + e2e |
| 4 | **P1-Override** | Tenant domain overrides update `operator_assigned_domains` + remount mappings (force re-map even from MAPPED) and `_build_jobs` honors `artifact.assigned_domain`. | Salesforce | Override students→staff then apply lands teachers |
| 5 | **P1-Verify** | Extend post-apply verification visible counts beyond students/staff/guardians/finance. | Salesforce | verification tests |
| 6 | **P1-Nav** | Tenant setup / studio / onboarding deep-link to `migration_cloud_connector:upload` (not only `school_setup_imports`). Dead-href strict scan. | Shopify | Named URL from nav + scan |
| 7 | **P1-Forensic** | `manage.py inspect_migration_tenant --slug=new-school` printing §2.2 classification. | Linux | Command + smoke |
| 8 | **P2** | DFV-only payroll/compliance: honest UI badges “stored as custom records”. | Shopify honesty | Template copy |
| 9 | **P2** | Legacy wizard deprecation banner pointing to connectionless MC. | Shopify | Template |
| 10 | **EXTERNAL** | FACTS/Skyward write paths, MAA v2 counsel flip | Counsel | Docket unchanged |

---

## Honest residuals

- **Prod bundle state for `new-school` unknown** until operator runs §2.2.  
- **Payroll / compliance** intentionally DFV — not first-class UI.  
- **MAA v2 / FACTS-Skyward writes** counsel-blocked.  
- **Offline MC upload** not in capability implementation gate.  
- Docstring in `landers/__init__.py` still claims Payslip/ComplianceCheck for payroll/compliance — **doc drift** vs lander honesty notes.

---

## Phase 0 sign-off

| Artifact | Path |
|----------|------|
| This audit | `docs/generated/migration_cloud_tenant_dominance_audit.md` |
| JSON twin | `docs/generated/migration_cloud_tenant_dominance_audit.json` |

**Next action:** Phase 1 implementation starting at **P0-A** (schema binding) then **P0-B** (companion ingest), with focused tests before any broader refactor.

---

## Phase 1–2 progress (same calendar day)

### P0-A shipped — schema binding
| Change | Path |
|--------|------|
| Canonical resolver | `apps/migration_cloud/schema_binding.py` |
| Wired intake/bind/companion/apply | views_tenant_upload, views, intake_init, connector_bundle_bridge, companion_receiver, orchestrator |
| Tests | `test_schema_binding_p0a.py` — **5 OK** |

### P0-B shipped — companion decrypt → ingest
| Change | Path |
|--------|------|
| Ingest service | `services/companion_plaintext_ingest.py` |
| Decrypt hook | `companion_receiver.py` calls ingest + advance; fails closed on ingest error |
| Tests | `test_companion_plaintext_ingest_p0b.py` — **9 OK** |

### P1-UX shipped — upload ≠ import
| Change | Path |
|--------|------|
| Upload copy + success toast | `upload.html`, `views_tenant_upload.py` |
| Review banner “Not in your school yet” | `bundle_review.html` |
| Tests | `test_tenant_ux_not_in_school_p1.py` — **3 OK** |

### P1-Override shipped — domain remount
| Change | Path |
|--------|------|
| Sync operator map + rewind PROFILED | `_sync_tenant_domain_overrides` |
| Apply prefers `artifact.assigned_domain` | `orchestrator._build_jobs` |
| Tests | `test_tenant_domain_override_p1.py` — **3 OK** |

### P1-Verify shipped — visible counts
| Change | Path |
|--------|------|
| Extended `_DOMAIN_MODELS` | `verification.py` (attendance/grades/behavior/sections/health/events/…) |
| Tests | `test_post_apply_verification_2026_07_12.py` updated — green |

### P1-Nav shipped — studio → MC upload
| Change | Path |
|--------|------|
| `school_studio_redirect_migration` | → `migration_cloud_connector:upload` |

### P1-Forensic shipped
| Change | Path |
|--------|------|
| `manage.py inspect_migration_tenant --slug=` | classifies bundles for support triage |
| Tests | `test_inspect_migration_tenant_p1.py` |

### P2 shipped — honesty
| Change | Path |
|--------|------|
| DFV badge for payroll/compliance | review template + context `dfv_only` |
| Legacy wizard deprecation banner | `accounts/migration_wizard.html` → MC upload |

### Still EXTERNAL (counsel / prod)
- Prod DB forensic for `new-school` (needs operator shell / Render DB)
- FACTS/Skyward write counsel + MAA v2 flip (**shovel-ready** — PDFs missing; do not fabricate)

### Closed in batch 1770
- Offline MC upload in capability matrix (SODP metadata + IndexedDB flush)

**Combined proof (2026-07-20):** 32 focused Django tests OK (P0–P1 suites) + P2 honesty + offline MC 6 OK; `scan_lander_phantom_fields` 0; `verify_migration_cloud_connectors` PASS; offline capability PASS 6.

---

## Closeout wave (same day — repo 100%)

Closes remaining **repo-contained** Shopify/AWS failure modes after P0–P2:

| Item | Status | Proof |
|------|--------|-------|
| Companion `next_step_url` host-aware (portal/super/connector) | DONE | `test_tenant_closeout_ux_2026_07_20.NextStepUrlTests` |
| Advance failure → `advance_error` in progress JSON + review banner | DONE | `_progress_payload` + `bundle_review.html` |
| Tenant **Retry detection** POST (`bundle-retry`) | DONE | `TenantMigrationRetryAdvanceView` + tests |
| Quarantine reason + empty CSV/ZIP row hints | DONE | `_row_hint` + template |
| Entitlement: `migration_cloud` on Growing+ plans (portal 402 gap) | DONE | `seed_subscription_catalog` + CatalogEntitlementCloseout |
| Operator runbook: `inspect_migration_tenant` in Command Center tip + docs | DONE | `MIGRATION_CLOUD_COMMAND_CENTER.md` + template tip |
| Playwright e2e upload-rail smoke (gated `MIGRATION_CLOUD_E2E`) | DONE | `tests/e2e/migration-cloud.spec.js` |
| Prod `new-school` DB forensic | **EXTERNAL** | Still needs Render shell |
| Offline MC upload (SODP + IndexedDB) | **DONE** | batch 1770 — capability matrix PASS |
| Counsel MAA v2 + FACTS/Skyward writes | **EXTERNAL (shovel-ready)** | PDFs required; promote/stubs intact |

**Tenant rail entitlement policy (locked):** Day-1 `/school/setup/migration-cloud/` remains **ungated** by plan capability (onboarding). Portal `/portal/configure/migration/` stays gated. Growing School and above seed `migration_cloud` so portal is not a surprise 402 for typical paid tenants after `seed_subscription_catalog`.
