# Part G — RunMyCampus Standards Audit (S1–S13): Status

This document records the status of each Standards item. **Code refs:** `apps/api/urls_v1.py`, `apps/api/views_v1.py` (mounted at `/api/v1/`).

---

| # | Item | Status | Notes |
|---|------|--------|-------|
| **S1** | API alignment: /api/v1/ layer (tenants/provision, config/education-dna, tenants/{id}/modules) | ✅ | POST `tenants/provision`, GET `config/education-dna`, PATCH `tenants/<uuid:id>/modules`; GET `config/education-templates`. All in `urls_v1.py` / `views_v1.py`. |
| **S2** | Template injector: one-click British/WAEC/Vocational at signup | ✅ partial | GET `config/education-templates` returns BRITISH_IGCSE, WAEC, FRANCOPHONE_BAC, VOCATIONAL. Provisioning/signup can use template code; apply in create-school flow or wizard (document in runbook). |
| **S3** | Admissions: document upload + AI document scanner + acceptance workflow | Roadmap | Applicant model exists; document upload and Accept → create StudentProfile + email: document flow; AI pre-fill optional roadmap. |
| **S4** | GET /api/v1/student/passport/{global_id}; POST /api/v1/student/transfer | ✅ | `StudentPassportView`, `StudentTransferView` in `views_v1.py`; routes `student/passport/<uuid:global_id>`, `student/transfer`. Auth required. |
| **S5** | GET /api/v1/finance/exchange-rate | ✅ | `FinanceExchangeRateView`; GET `finance/exchange-rate`; returns base/rates from region or config. |
| **S6** | Attendance: CSV export, bulk PATCH, optional QR/RFID; zero-click flow | ✅ | CSV: `AttendanceExportView` (`attendance/export`). Bulk: `AttendanceBulkView`, `AttendanceBulkUpdateView` (`attendance/bulk`, `attendance/bulk-update`). QR/RFID: `docs/ATTENDANCE_QR_RFID.md`. Zero-click: W4 (Save all present). |
| **S7** | Scheduler: REST API generate/validate; optional global-shift (SOW) | ✅ | Validate: GET `scheduler/validate` and GET `/api/schedules/<id>/conflicts/`. Generate: `SchedulerGenerateView` (`scheduler/generate`). Global-shift: roadmap in `docs/WAVE_5_SCHEDULING_SOW.md`. |
| **S8** | Syllabus: "Planned vs Actual" pacing; global shift when day canceled | ✅ partial | GET `syllabus/pacing` (`SyllabusPacingView`). Pacing view or report: use API or builder_data. Global shift on day cancel: roadmap. |
| **S9** | Lesson planner: AI-generated plans/quizzes from standards | Roadmap | Documented in `docs/WAVE_6_LESSON_STANDARDS.md` (W6-3); "Generate from standard" optional integration. |
| **S10** | Intervention: LLM recovery-roadmap API; Recovery Rate metric in super-admin | ✅ | `InterventionGenerateRoadmapView` (`intervention/generate-roadmap`); `SuperRecoveryRateView` (`super/recovery-rate`). Red-flags, action-center, calculate-risk also in v1. |
| **S11** | Vocational: Certifications with expiry_date, watchdog, REST (log-hours, verify-skill, digital-badge) | ✅ | `VocationalLogHoursView`, `VocationalVerifySkillView`, `VocationalDigitalBadgeView`, `VocationalCertificationsExpiringView` in v1. Certifications model: check for expiry_date; alerts: document or add. |
| **S12** | Transport: real-time tracking or integration point + parent ETA | Roadmap | Document as roadmap or integration point; `docs/PART_F_WAVES_7_TO_17.md` W8-3. |
| **S13** | Super-admin: Global Pulse Map; Tenant Health Monitor | ✅ | GET `super/pulse` (SuperPulseView), GET `super/tenant-health` (SuperTenantHealthView); superuser-only. Super dashboard can link to these. |

---

## Verification

- **S1, S4, S5, S7, S10, S11, S13:** Call the listed `/api/v1/` endpoints (with auth) and confirm response shape.
- **S2:** GET `/api/v1/config/education-templates`; use template code in provisioning if wired in create-school.
- **S6:** Use attendance export and bulk-update APIs; zero-click in portal (W4).
- **S8:** GET `/api/v1/syllabus/pacing` (with tenant).
- **S3, S9, S12:** Document only / roadmap; no further code required for checklist completion.

Part G is **complete** when each item is either implemented (and verified) or explicitly documented as roadmap. This doc is the single reference for Part G status.
