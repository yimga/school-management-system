# Buea/Cameroon SMS Guideline Audit

This document maps the **Implementing a School Management System (SMS) in Buea, Cameroon** guideline and common SMS issues to the current codebase. It shows what is **addressed**, what is **partial**, and what remains as **gaps** with concrete references and recommendations.

**Technology stack:** Python/Django (backend), Django templates + JS (frontend), SQLite/PostgreSQL, REST API for mobile/offline.

---

## 1. Workflow & Contextual Issues (Buea)

### 1.1 Lack of Offline Synchronization

| Guideline | Technical solution | Status | Where in codebase |
|-----------|--------------------|--------|--------------------|
| Unstable internet; avoid lost work | Service Workers + offline sync | **Addressed** | `portal_base.html` registers `static/js/service-worker.js`; PWA caches static assets and serves cached API responses when offline. |
| Local caching / offline data entry | Offline sync for marks + API | **Addressed** | `apps/evals/offline_sync.py` (OfflineSyncService); `OfflineMarkEntry` model; conflict resolution (reject / auto_merge / show_both). Site setting: `enable_offline_mode`, `offline_sync_conflict_resolution`. |
| Sync API for mobile | REST sync endpoint | **Addressed** | `apps/api/urls.py`: `OfflineSyncViewSet` at `/api/sync/`. See `apps/api/mobile_api.py` and `docs/MOBILE_API_HANDBOOK.md`. |

**Gap:** Service worker currently caches API GET responses; **IndexedDB** for structured offline form drafts (e.g. attendance batch) is not implemented. Recommendation: extend mobile/offline docs and consider IndexedDB for large form drafts if needed.

---

### 1.2 Power-Dependent Workflows / Auto-Save

| Guideline | Technical solution | Status | Where in codebase |
|-----------|--------------------|--------|--------------------|
| Auto-save to avoid loss on power cut | Client-side storage + recovery | **Partial** | Theme/sidebar/layout preferences use `localStorage` (e.g. `portal_base.html`, `phase7-theme.js`, `dashboard-layout.js`). No generic form auto-save to IndexedDB for long forms. |
| Low-power devices (tablets/phones) | Responsive UI, PWA | **Addressed** | PWA support; responsive CSS; mobile-friendly portal and teacher dashboards. |

**Addressed (optional):** Generic form draft save for mark entry: `static/js/form-draft-save.js` saves the marks form to `localStorage` (debounced); on next load, if a draft exists and is under 24h old, a "Resume draft?" banner offers Restore or Discard. The teacher mark entry form uses `data-draft-key="marks_{subject_assignment_id}"`. Reduces data loss on power cut or closed tab.

---

### 1.3 Overcrowded Data Handling / Bulk Processing

| Guideline | Technical solution | Status | Where in codebase |
|-----------|--------------------|--------|--------------------|
| Mass attendance | Bulk attendance API | **Addressed** | `apps/academics/api_views.py`: `AttendanceViewSet.create` accepts `records[]`; teacher role validated; server-side student-in-classroom checks. |
| Mass exam marks | Bulk grade import | **Addressed** | CSV import: `apps/evals/views.py` (`grade_import_apply_api`), `apps/evals/importers.py`, `apps/evals/import_services.py`. Role: admin/head_of_academics. Bulk evaluation create in evals views. |
| Bulk student/guardian creation | Entity API bulk-commit | **Addressed** | `apps/api/entity_api.py`: `StudentProfileViewSet.bulk_commit`, `StudentGuardianViewSet.bulk_commit`; `max_bulk_import_rows` (site config, default 500). |
| Bulk letters | Reports / mail-merge | **Addressed** | `apps/siteconfig/views.py`: `bulk_letters`; RBAC in `test_report_library_bulk_letters.py`. |
| Bulk finance access | Bulk grant guardian access | **Addressed** | `apps/finance/views.py`: `finance_access_bulk`; audit-friendly notifications. |

**Addressed (optional):** Bulk attendance API accepts a list of records in one request; for very large classes (e.g. 80+), consider splitting into multiple requests (e.g. 50 per request) if the school reports timeouts. Documented in this audit as an operational note; no hard server limit is enforced.

---

### 1.4 Manual Admission Overload / Ghost Students

| Guideline | Technical solution | Status | Where in codebase |
|-----------|--------------------|--------|--------------------|
| Automated online registration | Student onboarding wizard | **Addressed** | `apps/portal/views_onboarding.py`: `student_onboarding_wizard`; `StudentOnboardingForm` in `apps/portal/forms.py`. Route: `/portal/student/onboarding/`. |
| Admission number validation | Auto or manual, pattern, duplicate check | **Addressed** | `SiteSettings.admission_number_mode`, `admission_number_pattern`; validation in `StudentOnboardingForm.clean_admission_number` and backend. See `docs/ADMISSION_NUMBER_GUIDE.md`. |
| Guardian invite / claim | Reduce manual linking | **Addressed** | PendingGuardianInvite, claim flow at `/portal/claim-invite/`; link-child wizard. |

**Gap:** None. Onboarding and admission number handling are documented in `docs/WORKFLOW_STUDENT_ONBOARDING.md`, `docs/ONBOARDING_FLOW_GUIDE.md`.

---

## 2. Common Code-Level Flaws

### 2.1 Database Scalability / Indexing

| Guideline | Technical solution | Status | Where in codebase |
|-----------|--------------------|--------|--------------------|
| Efficient indexing as DB grows | Indexes on key lookups | **Addressed** | Migrations add indexes (e.g. `people/migrations/0010_add_performance_indexes.py`). Finance, evals, and compliance models use `db_index` / `Meta.indexes` where needed. |
| Caching for heavy queries | Rankings, site settings, compliance | **Addressed** | `cache_rankings_interval_minutes`; `SiteSettings` in-memory cache; compliance access control cache; dashboard widget cache. |

**Gap:** Periodic review of slow-query logs and adding indexes for new report/analytics queries is recommended.

---

### 2.2 Weak RBAC (Teacher / Bursar / Admin)

| Guideline | Technical solution | Status | Where in codebase |
|-----------|--------------------|--------|--------------------|
| Strict role separation | Permission checks + role decorators | **Addressed** | `@permission_required`, `@staff_member_required`, `@role_required` used widely (accounts, evals, finance, siteconfig, reports). |
| Teacher vs admin grade edits | Grade approval workflow | **Addressed** | `apps/evals/approval.py`; grade post roles vs approval roles; audit trail. |
| Finance data isolation | Finance permissions + audit | **Addressed** | Finance views check permissions; `FinanceRequestAudit`, `PaymentAuditLog`; access request workflow. |

**Gap:** None. See `apps/accounts/permissions.py`, `apps/accounts/decorators.py`, and role templates in migrations.

---

### 2.3 Hardcoded Configuration

| Guideline | Technical solution | Status | Where in codebase |
|-----------|--------------------|--------|--------------------|
| No hardcoded server paths or DB credentials | Env-based config | **Addressed** | `config/settings.py` uses `os.getenv()` for SECRET_KEY, DATABASE_URL, DB_FILE, EMAIL_*, CACHE_*, REDIS_URL, CELERY_BROKER_URL, LOG_LEVEL, etc. `.env.local` loaded via python-dotenv. |
| Move between local server and cloud | Same codebase, env swap | **Addressed** | Documented in deployment docs; `docs/CAMEROON_BUEA_SETUP_GUIDE.md` for Buea. |

**Gap:** Ensure `.env.example` lists all required variables (see project root). No credentials in repo.

---

### 2.4 Insufficient Error Logging / Graceful Degradation

| Guideline | Technical solution | Status | Where in codebase |
|-----------|--------------------|--------|--------------------|
| Log where process stopped on failure | Structured logging | **Addressed** | `logger` / `logging` used across apps (evals, finance, compliance, automation, observability, api). |
| Graceful degradation | Cache fallback, try/except in critical paths | **Partial** | AI copilot and some APIs degrade on audit-log failure; cache misses handled. Celery tasks have retries. |
| Request/audit logging | Middleware | **Addressed** | `apps.compliance.middleware.AuditLoggingMiddleware`; compliance dashboard and observability use `AuditLog`, `AccessLog`. |

**Gap:** Ensure all critical finance/grade paths log exceptions with context (user, entity id). Optional: add a "last failed step" field for long-running jobs (e.g. bulk import).

---

## 3. Structural & Strategic Alignment

### 3.1 Modular vs Monolithic / CFA and Mobile Money

| Guideline | Technical solution | Status | Where in codebase |
|-----------|--------------------|--------|--------------------|
| CFA / MTN / Orange Money without rewriting core | Modular payment methods | **Addressed** | `PaymentMethodCode.MTN_MOMO`, `ORANGE_MOMO`; `apps/finance/bank_verification.py` (MTN MoMo, Orange Money); `apps/finance/tasks.py` (payment instructions, verification); Site Settings: `finance_payment_instructions_mtn_momo`, `finance_payment_instructions_orange_money`. |
| Bank deposit verification | Cameroon-specific flows | **Addressed** | `docs/BANK_DEPOSIT_VERIFICATION_AND_IMPROVEMENTS.md`; `docs/CAMEROON_BUEA_SETUP_GUIDE.md`. |

**Gap:** None. MTN/Orange API keys are optional; manual entry works without them.

---

### 3.2 Training / Digital Literacy

| Guideline | Technical solution | Status | Where in codebase |
|-----------|--------------------|--------|--------------------|
| Deploy with staff training in mind | Docs, KB, FAQs | **Addressed** | KB articles, FAQs, onboarding guides; `docs/WORKFLOW_*.md`, `docs/ONBOARDING_FLOW_GUIDE.md`, `docs/FAQS_COMPREHENSIVE.md`. Portal help and feature visibility can be tuned. |

**Gap:** Consider in-app "first-time" hints or short video links for Buea (e.g. mark entry, fee reminder).

---

## 4. Summary Table (Guideline Critical Vulnerabilities)

| Category | Local challenge | Technical solution | Status |
|----------|-----------------|--------------------|--------|
| **Connectivity** | Unstable internet | Service Workers + offline sync API + PWA | Addressed |
| **Infrastructure** | Power cuts | localStorage for prefs; form draft save for mark entry (Resume draft) | Addressed |
| **Financials** | Manual fee tracking | MTN MoMo / Orange Money support; payment codes; reminders with instructions | Addressed |
| **Security** | Unauthorized grade edits | Server-side validation; grade approval; audit logs (GradeAudit, AuditLog) | Addressed |

---

## 5. Common Workflow Issues (General SMS)

| Issue | Status | Where in codebase |
|-------|--------|--------------------|
| Manual data entry / duplication | Addressed | Single student record; onboarding feeds profile; guardian link once. |
| Inefficient onboarding/offboarding | Addressed | Student onboarding wizard; guardian invite/claim; bulk entity API. |
| Poorly designed attendance | Addressed | Bulk attendance API; teacher-scoped; real-time capable. |
| Communication bottlenecks | Addressed | Notifications (finance reminders, deadline reminders, evals); notification channels in site config; WhatsApp deep links. |
| Rigid timetable | Partial | Academics/timetable models exist; last-minute change workflows not fully audited here. |
| Data silos / no integration | Partial | REST API for mobile/dashboard; webhooks for payments; no prebuilt LMS/accounting sync. |
| Scalability limitations | Addressed | Indexing; caching; bulk APIs; configurable limits. |
| Security & privacy / audit trails | Addressed | RBAC; AuditLog; GradeAudit; PaymentAuditLog; FinanceRequestAudit; FeatureControlAudit. |
| Hardcoded customizations | Addressed | Site Settings; feature flags; theme/region config. |
| Performance bottlenecks | Addressed | Caching; bulk operations; rate limiting; optional Redis. |
| Inadequate reporting/analytics | Addressed | Analytics app; reports; master sheet; BI; dashboard APIs. |

---

## 6. Recommendations Summary

1. **Done:** Form draft save for mark entry: `static/js/form-draft-save.js` + marks entry form with "Resume draft?" banner (24h max age). Reusable for other forms via `data-draft-key` and `FormDraftSave.init(form)`.
2. **Done:** Bulk attendance: no hard server limit; for 80+ students per class, chunking (e.g. 50 per request) is an operational recommendation if timeouts occur.
3. **Maintain:** Keep all config in env; keep `.env.example` up to date.
4. **Maintain:** Ensure every critical grade/finance path logs exceptions with enough context for local IT to troubleshoot.
5. **Optional:** Add a short "Buea checklist" to `docs/CAMEROON_BUEA_SETUP_GUIDE.md` that links to this audit and highlights offline, payments, and RBAC.

---

## 7. References

- **Offline / PWA:** `static/js/service-worker.js`, `portal_base.html` (PWA block), `apps/evals/offline_sync.py`, `apps/api/mobile_api.py` (OfflineSyncViewSet)
- **Form draft save (power loss):** `static/js/form-draft-save.js`, `templates/teacher/marks_entry.html` (data-draft-key, Resume draft banner)
- **Config:** `config/settings.py` (env vars), `.env.example`, `docs/CAMEROON_BUEA_SETUP_GUIDE.md`
- **Payments:** `docs/BANK_DEPOSIT_VERIFICATION_AND_IMPROVEMENTS.md`, `docs/PAYMENT_RECEIPT_AUTOMATION_PLAN.md`, `apps/finance/bank_verification.py`, `apps/finance/tasks.py`
- **RBAC / Audit:** `apps/accounts/permissions.py`, `apps/compliance/models_audit.py`, `apps/evals/approval.py`, `apps/finance/models.py` (PaymentAuditLog, FinanceRequestAudit)
- **Bulk / Onboarding:** `apps/api/entity_api.py`, `apps/academics/api_views.py`, `apps/portal/views_onboarding.py`, `docs/WORKFLOW_STUDENT_ONBOARDING.md`
