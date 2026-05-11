# Multi-tenant / global SaaS roadmap

Status: Passes 1–5 complete (multi-tenant residue mostly purged, region/currency/grading
defaults made neutral, +237 / XAF / FCFA / DD-MM-YYYY / hardcoded `$` removed from the
hot paths, SIS interop adapters route through tenant grading scale, flash-message i18n
scrub on the most visible 6 views).

Two large bodies of work remain. Both touch schema and core UX and are explicitly
flagged here rather than executed in-flight because they require user approval:
they involve default-on flips, new core entities, multi-week effort, and migrations
that will affect every tenant.

---

## Pass 6 — Offline-first foundational wiring

**Goal:** Make the platform truly local-first for teachers/parents in low-connectivity
regions. Today the *write* pipeline is real (SW outbox + delta sync + `SyncConflict`)
but the *read* mirror is dead code, grades are excluded, the API endpoint the SW
queues to does not exist, the PWA is not installable, and the whole system is opt-in.

### BLOCKING gaps (audit-confirmed)

| # | Item | Files | Effort |
|---|---|---|---|
| 1 | Wire `SMSOfflineDB` into pages that need read-offline (teacher dashboard, attendance entry, parent dashboard, child marks view). New `static/js/offline-bind.js` reads from IndexedDB when `navigator.onLine === false`. | `templates/teacher/dashboard.html`, `templates/teacher/attendance.html`, `templates/parent/dashboard.html`, new `static/js/offline-bind.js`, `static/js/offline-db.js` | M (1-2 weeks) |
| 2 | Flip `enable_offline_mode` default to `True` on `PlatformSiteSettings`. | `apps/platform_runtime/models.py:364`, new migration | S (1 day) |
| 3 | Add the missing `POST /api/attendance/` endpoint that the SW queues to. Audit `apps/api/urls.py` for `/api/attendance/`, `/api/grades/`, `/api/evals/` writeable + tenant-scoped routes. | `apps/api/urls.py`, `apps/api/entity_api.py` | S-M (3-5 days) |
| 4 | Uncomment grades in SW write list and extend `_get_entity_config` with `grade_entry` / `lesson_note` / `student_comment`. | `static/js/service-worker.js:287,295`, `apps/api/sync_services.py:14-37`, `apps/sync_engine/conflict_resolver.py:34` | S (2-3 days) |
| 5 | Fresh-CSRF-on-replay path: new `/api/csrf/` view, update `service-worker.js:replayQueue` to fetch a fresh `X-CSRFToken` before replay (or route all queued writes through the existing `/api/offline/replay_batch/` Django test-client bypass). | `apps/api/views_csrf.py` (new), `static/js/service-worker.js:525` | S (2-3 days) |
| 6 | Make PWA installable: ship 192/512 PNG icons, register `start_url: "/portal/?source=pwa"`, set scope, theme color from tenant primary. | `static/manifest-portal.json:10`, `static/icons/portal-192.png`, `static/icons/portal-512.png` | S (1-2 days) |

### DEGRADED gaps

- Tenant-scoped IndexedDB queue: `SYNC_DB_NAME = "sms-offline-sync-db-tenant-${schoolId}"` so switching tenants on shared devices does not replay writes against the wrong school.
- Pull-delta API: `?since=<ISO>` parameter on `/api/entities/students/`, `If-Modified-Since` on GETs; `auto-pilot.js` re-fetches full list endpoints today (tens of MB/day for a 2000-student school).
- Conflict workbench UI: promote `templates/portal/offline_sync_conflicts.html` from a localStorage list into a real diff/resolve page over `SyncConflict.objects.filter(status=PENDING)`.
- Periodic Background Sync registration (gated by browser permissions the app never requests).
- E2E coverage: expand `tests/e2e/offline-sync.spec.js` (currently 4 happy-path tests) to fault-inject across attendance / grades / parent dashboard / admin lookup.

### Optional cherry

- Capacitor wrapper at `/mobile/` reusing the same SW for OS-level background sync and >1GB storage. Useful for rural schools uploading attendance photos.

---

## Pass 7 — Education-system rebuild (de-Cameroonize the model layer)

**Goal:** Convert "nameplate" coverage (Board enum entries) into real differentiated
support for each major education system. Today only Cameroon GCE has actual content;
WAEC/NECO/KCSE/CBSE/IGCSE/IB/AP/Bac/Abitur/ACARA are slugs with empty `policy_snapshot`.

### TOP-5 BUILD priorities (audit-recommended)

1. **De-Cameroonize `evals.Evaluation`.** Remove `seq1_score / seq2_score / exam_score / mock_score / practical_score / internship_score` + `MaxValueValidator(20)`. Replace with `EvaluationComponent` child table referencing `GradingScale` + `AssessmentWeights` per system. **Single highest-impact change** — unblocks IB 1-7, Abitur Punkte, IGCSE A*-G, KCSE A-E, GPA 4.0 weighted.
   - Files: `apps/evals/models.py:354-600`, new migration that maps existing rows.
   - Effort: L (3-4 weeks)
2. **`SpecialEducationPlan` + `FerpaDisclosureLog`.** Required for US K-12 public sale.
   - Files: `apps/compliance/` (already houses `ConsentRecord`).
   - New models: `SpecialEducationPlan` (IEP/504/IDEA-Part-B + goals/services/accommodations/annual-review-date), `FerpaDisclosure` (record_id, accessor, purpose, legitimate-interest flag, timestamp).
   - Effort: M (2 weeks)
3. **First-class `Assignment` + `Submission` LMS spine.** Without this, lose to Schoology/Google Classroom/Canvas in every market.
   - Files: new `apps/learning/` app or extend `apps/academics/`.
   - New: `Assignment`, `AssignmentSubmission`, `Rubric`, `RubricCriterion`, `SubmissionAttachment`.
   - Effort: L (4-6 weeks)
4. **Admissions pipeline upgrade.** Expand `people.Applicant:1010` (30 lines today) into a Veracross-class pipeline.
   - New: `Application`, `ApplicationStep`, `ApplicationDocument` (reuse `CertificationDocumentItem` pattern), `EnrollmentContract`, `ApplicationReference`, `ApplicationDecisionLetter`.
   - Effort: M (2-3 weeks)
5. **Populate the empty country policy_snapshots.** `seed_blueprint_policy_packs.py:150-184` ships WAEC/KCSE/CBSE/ACARA/UK-GCSE/IB/etc. as bare slugs. Wire each to a populated `policy_snapshot` (`grading_scale_ref`, `subject_group_taxonomy`, `term_calendar`, `mock_to_final_rules`, `exam_registration_pack`, `compliance_codes`). The pattern in `apps/policies/exam_pack_content.py` works — copy it 11 more times.
   - Effort: M (2-3 weeks, mostly content authoring)

### Audit-flagged secondary gaps

- `Incident` is unidimensional (TARDINESS/BEHAVIOR/ABSENCE/OTHER). Missing: house points, merit/demerit ledger, restorative-justice workflow, detention/suspension entity, points-balance.
- `HealthRecord` is one flat row. Missing: `Immunization` model + vaccine-schedule compliance, `Allergy` / `MedicalCondition` as first-class entities, medication-administration log.
- `LibraryItem` is books only. Missing: `LibraryReservation`, ISBN-lookup, fine/overdue policy, MARC import.
- `CurriculumStandard.country_code` is a free CharField. Missing: `external_framework_code`, `ceds_id`, `common_core_code` — districts cannot import their state standards.
- No `CounselingSession`, `WellnessLog`, `TherapyNote`, `ConferenceBooking`, `TranslationRequest`, `AlumniProfile`, `PredictedGrade`, `SubjectCombination` / stream selector.
- Middle East: `RegionConfig.CALENDAR_CHOICES` lists `islamic` but `AcademicYear` has no Hijri date field; `is_rtl` flag exists but no RTL-aware PDF template registered; no `WeekendPolicy` model (Fri-Sat schools cannot model attendance).

### Regional unlock priorities (audit-recommended)

| Market | Hardest blockers | Unlock |
|---|---|---|
| US K-12 public | No IEP/504, no FERPA log, `Evaluation` can't do weighted GPA, no Ed-Fi XML writer, no per-state report card | `SpecialEducationPlan`, `FerpaDisclosureLog`, `WeightedGPAConfig`, Ed-Fi adapter on `EMISSubmission`, per-state report-card templates |
| IB World School | `Evaluation` is 0-20 fixed, can't represent 1-7 + 3 core points, no `InternalAssessment` separate from final, no `PredictedGrade`, no CAS/EE/TOK tracking, no `subject_group` on Subject | Rebuild `Evaluation` polymorphically against `GradingScale`, add `IBCoreComponent`, add `SubjectGroup` FK on `Subject` |
| Middle East (UAE/Saudi/Qatar) | No Hijri-date on `AcademicYear`, no `weekend_days` on `RegionConfig`, no `KHDAInspection`, no Arabic/Islamic-studies core, no RTL-aware PDF | `WeekendPolicy`, Hijri-aware AcademicYear, KHDA report writer, Arabic L1/L2 on Subject, RTL report templates |

---

## How this rolls out

- **Pass 6** is a 4-6 week effort and can ship as a sequence of small commits behind the
  `enable_offline_mode` flag, finishing with the default-on flip. Lowest blast-radius
  approach: wire read-binding first (item 1) and ship installable PWA (item 6) before
  flipping the default, so users can install and test before the platform-wide change.
- **Pass 7** is a multi-quarter program. Recommended sequencing: priority #1 (de-Cameroonize
  `Evaluation`) ships first as a feature-flagged dual-write migration, then priorities 2-5
  ship in parallel tracks once the polymorphic grading foundation is stable.
- Neither pass should block customer demos. The platform is shippable today against
  passes 1-5; passes 6-7 expand the addressable market from "African private schools" to
  "global multi-tenant SaaS competing with PowerSchool / Veracross / Schoology".
