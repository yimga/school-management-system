# Part F — Waves 7–17: Status and Code Refs

This document is the single reference for **Part F (Waves 7–17)** completion. For each wave we record what is **implemented** (with code refs), what is **roadmap**, and how to verify.

---

## W7 — Admin Command Center

| Sub-item | Status | Notes |
|----------|--------|------|
| W7-1 Finance dashboard (overview, overdue) | ✅ | `apps/finance/views.py` — `dashboard()`; `finance_dashboard_data()` in `apps/finance/services.py` returns summary with receivables, paid, **overdue** count. Hero stats include "Overdue (Invoices late)". `finance:dashboard`, `templates/finance/dashboard.html`. API: `FinancialDashboardAPI`, `FinancialAnalyticsAPI` in `apps/api/dashboard_api.py`, `apps/finance/api_views.py`. |
| W7-2 Overdue list + reminders | ✅ | Overdue list: `finance:invoices` with `?status=OVERDUE`. Reports: `finance_reports()` shows `overdue_by_class`. Tasks: `apps/finance/tasks.py` — `update_invoice_statuses` marks overdue; `resend_reminder` per invoice in views. |
| W7-3 Staff matrix view | Roadmap | No dedicated "staff matrix" page yet. Admin: User list and PayrollEmployee/TeacherProfile changelists. Roadmap: backend view that lists staff by role/department with assignments. |
| W7-4 Leave overlay (calendar or list) | ✅ | Employee leave: `payroll:employee_leave` — list of current user's leave requests. Admin: LeaveRequest in payroll admin. Roadmap: admin "all staff leave" calendar overlay. |
| W7-5 RBAC visibility and lifecycle | ✅ | `docs/RBAC_AUDIT_CHECKLIST.md`, `apps/accounts/permissions.py`, Backend → RBAC & Access Control. Role templates and feature permissions; lifecycle = user/role management in admin. |

**Verification:** Open `/finance/` (dashboard), `/finance/invoices/?status=OVERDUE`, `/payroll/employee/leave/`; confirm RBAC doc exists.

---

## W8 — Staff Operations

| Sub-item | Status | Notes |
|----------|--------|------|
| W8-1 Admissions filters | Roadmap | Admissions/applicant models exist (`apps/people/models.py` Applicant). Filters (by status, date, program) in admin or dedicated admissions list: roadmap. |
| W8-2 Inventory/library borrow-return | ✅ partial | `StudentResourceReturn` (people), report card gated by "all issued resources returned" (`reports/services.py`). Full inventory/library module: roadmap. |
| W8-3 Transport alerts | Roadmap | Transport model (e.g. `uses_transport` on StudentProfile). Alerts (e.g. bus delay, ETA): integration point or doc. See `docs/ATTENDANCE_QR_RFID.md` style. |
| W8-4 Device management (optional) | Roadmap | Optional; document as roadmap or stub in config. |

**Verification:** Resource return in people/reports; rest documented as roadmap.

---

## W9 — Parent Engagement

| Sub-item | Status | Notes |
|----------|--------|------|
| W9-1 Progress card view | ✅ | Parent results: `portal:parent_dashboard` (results), `parent_child_results`; report cards in reports app. |
| W9-2 Attendance alerts | ✅ | W4-4: Notification to guardians when student absent (`apps/academics/signals.py`). |
| W9-3 One-click payment + receipt | ✅ | Parent finance: `portal:parent_finance`; invoice list, pay; receipt via `finance:invoice_receipt`. Payment gateways (MoMo, etc.) in finance. |
| W9-4 Communication hub | ✅ | `portal:parent_contact_school`, announcements, feed; communication app. |
| W9-5 Photo search (optional) | Roadmap | Photo upload/search in portal: optional; roadmap. |

**Verification:** Parent portal: Finance, Messages, Feed, Attendance; payment and receipt flows.

---

## W10 — Requests, Automation, Calendar

| Sub-item | Status | Notes |
|----------|--------|------|
| W10-1 Unified requests dashboard | ✅ | `requests:dashboard` — `apps/requests/views.py` `requests_dashboard`, `templates/requests/dashboard.html`. |
| W10-2 Automation visibility (list/log) | Roadmap | Celery tasks and management commands exist; no unified "automation log" UI. Roadmap: list of recent task runs or automation events. |
| W10-3 Unified school calendar | ✅ | `portal:unified_calendar` — `apps/portal/views.py` `unified_calendar`, `_merged_upcoming_events` in portal services. |

**Verification:** `/requests/`, `/portal/calendar/`.

---

## W11 — API Center, Webhooks, EMIS, LTI

| Sub-item | Status | Notes |
|----------|--------|------|
| W11-1 API Center (keys, docs) | ✅ | `apps/apicenter` — dashboard, toggle integrations; `config/urls.py` `api-center/`. API keys/permissions in accounts/siteconfig. Schema: `api/schema/`, `api/schema/ui/`. |
| W11-2 Webhooks (outgoing, logs) | ✅ | `WebhookDelivery` (siteconfig), `dispatch_webhook_deliveries` command; `apps/siteconfig/webhook_delivery.py`; finance webhook for payments. |
| W11-3 EMIS export alignment | ✅ partial | `emis` app; OneRoster/SCIM/export stubs. Align to local EMIS format: configurable/roadmap. |
| W11-4 LTI integration point | ✅ | LTI 1.3 launch, AGS, NRPS, deep linking in config URLs; `lti/` routes. |

**Verification:** `/api-center/`, API schema UI; webhook delivery in siteconfig; LTI launch URL.

---

## W12 — Observability, Retention, Backup

| Sub-item | Status | Notes |
|----------|--------|------|
| W12-1 Tenant health metrics | ✅ | `apps/observability/views.py` — health, SLO dashboard; `api/health/`, `api/observability/`. |
| W12-2 Retention/purge (GDPR/compliance) | ✅ | Compliance purge: `purge_compliance_data` command; retention in `apps/accounts/management/commands/security_log_retention.py`; compliance app. |
| W12-3 Backup runbooks | Roadmap | Document backup/restore procedures (DB, media) in runbook; no code change. |
| W12-4 Redis cache usage/docs | Roadmap | Settings and cache usage; document Redis usage for sessions/cache in deployment doc. |

**Verification:** Health endpoint; purge/retention commands; add runbook doc if missing.

---

## W13 — SSO, Push, Exports, Notification Center

| Sub-item | Status | Notes |
|----------|--------|------|
| W13-1 SSO config and login | ✅ | Part A B5: SSO buttons on login when SAML/OIDC; `LOGIN_SSO_INTEGRATIONS` in context. |
| W13-2 Push notification delivery | ✅ partial | PushNotificationViewSet, mobile API; delivery pipeline: communication channels. Expand as needed. |
| W13-3 Exports (reports, data) | ✅ | CSV/PDF exports across finance, evals, reports, analytics; compliance export pack. |
| W13-4 Notification Center UI | ✅ | Notifications in portal/backend; `api/notifications/`; bell/dropdown in templates. |

**Verification:** Login with SSO; exports from reports/finance; notifications API and UI.

---

## W14 — Global Differentiators

| Sub-item | Status | Notes |
|----------|--------|------|
| W14-1 normalized_value / Rosetta | ✅ | `apps/api/rosetta_views.py` — RosettaStoneConvertAPI, RosettaStoneScalesAPI; grade conversion. |
| W14-2 Curriculum templates | ✅ partial | CurriculumStandard, CurriculumNode; templates (British/WAEC/Vocational): signup template injector in Part G S2. |
| W14-3 Compliance engine | ✅ | Compliance app: access log, audit, GDPR export, purge; alerts. |
| W14-4 AI narrative (reports) | Roadmap | AI copilot exists; narrative reports from AI: roadmap. |
| W14-5 RTL support | ✅ partial | `RegionConfig.is_rtl`; RTL in templates/context: partial; expand as needed. |
| W14-6 Subscription/hierarchy | Roadmap | School hierarchy or multi-school subscription: model/feature flags; roadmap. |
| W14-7 Transcript vault | ✅ partial | Transcripts in reports/evals; "vault" (immutable store): roadmap. |

**Verification:** Rosetta API; compliance dashboard; RTL config.

---

## W15 — Performance

| Sub-item | Status | Notes |
|----------|--------|------|
| W15-1 Redis tenant-config cache | ✅ | Redis in `config/settings.py`; `site_settings_v1` cache in `apps/siteconfig/middleware/maintenance_mode.py`. **docs/W15_PERFORMANCE.md** documents tenant-config cache pattern. |
| W15-2 High-traffic hardening | ✅ | **docs/W15_PERFORMANCE.md** includes hardening checklist (Redis, DB pooling, CDN, rate limits, Celery, N+1, health). |

**Verification:** See `docs/W15_PERFORMANCE.md`.

---

## W16 — Canteen & Cahier

| Sub-item | Status | Notes |
|----------|--------|------|
| W16-1 Configurable modules (feature flags) | ✅ | Feature gates: `FEATURE_GATE_PATH_MAP`, `feature_registry`; modules per school. |
| W16-2 Minimal canteen flow | Roadmap | Canteen (meals, payments): optional module; roadmap or stub. |
| W16-3 Cahier (journal) minimal flow | ✅ | `CahierDeTexteEntry` (portal); teacher diary; visa workflow. `portal` views: cahier_list, cahier_verify_list, cahier_visa. |

**Verification:** Feature flags in middleware; Cahier views in portal.

---

## W17 — Final Certification

| Sub-item | Status | Notes |
|----------|--------|------|
| W17-1 Full regression suite run | Roadmap | Run pytest/CI full suite before release; document in release checklist. |
| W17-2 Security/compliance evidence pack | ✅ | `compliance/management/commands/export_compliance_evidence_pack.py`; compliance reports. |
| W17-3 Rollout/rollback procedure | Roadmap | Document in deployment/runbook. |
| W17-4 Cutover checklist | Roadmap | Document in release checklist (see W0-3). |

**Verification:** Export evidence pack; add rollout/cutover to docs when releasing.

---

## Summary

- **Implemented (code exists):** W7-1, W7-2, W7-4, W7-5; W8-2 partial; W9-1–W9-4; W10-1, W10-3; W11-1–W11-4; W12-1, W12-2; W13-1–W13-4; W14-1, W14-2 partial, W14-3, W14-5 partial, W14-7 partial; W16-1, W16-3; W17-2.
- **Roadmap (documented, no or minimal code):** W7-3 (staff matrix), W7-4 admin leave overlay; W8-1, W8-2 full, W8-3, W8-4; W9-5; W10-2; W12-3, W12-4; W14-4, W14-6; W16-2; W17-1, W17-3, W17-4. W15-1/W15-2: doc in **W15_PERFORMANCE.md**.

Part F is **complete** in the sense that every wave is accounted for: existing features are documented with refs, and remaining work is explicitly roadmap. Use this doc for handoff and to prioritize future implementation.
