# EdOS Academic and Student Journey OS

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_ACADEMIC_JOURNEY_OS_READY`

## Scope

Refactors academics + evals + reports + student360 + school_events + dportal + dashboard. Multi-syllabus architecture + grading schema abstraction + polymorphic grading engine + multi-curriculum matrix + report card factory posture + transcript proof posture + attendance workflows + marks workflows + micro-grading matrix + quick comment tags + continuous micro-progress timeline + homework support guard + polymorphic learning queue + teacher workflows + parent/student portals + academic calendar localization + learning/LMS posture + data quality warnings + AI support (only if safe) + NO answer leakage.

## Sections

### Engine components

- Multi-syllabus — CBSE/ICSE/IGCSE/IB/Bac/GCE/state-boards/Quebec PIPEDA/108課綱/CÉGEP
- Grading schema abstraction — GradingScale registry per syllabus
- Polymorphic grading engine — apps.evals.polymorphic_grading_engine
- Multi-curriculum matrix — apps.academics curriculum_matrix
- Report card factory — apps.reports.report_card_factory with template registry
- Transcript proof — HMAC-SHA512 transcript signature + replay-safe
- Attendance workflows — apps.academics + attendance.hash_proof_created event
- Marks workflows — apps.academics + apps.evals
- Micro-grading matrix — apps.evals.micro_grading_matrix
- Quick comment tags — apps.evals.comment_tag_registry
- Continuous micro-progress timeline — apps.evals.micro_progress_timeline
- Homework support guard — apps.academics.homework_support_guard (NO answer leakage)
- Polymorphic learning queue — apps.academics.polymorphic_learning_queue per student profile
- Teacher workflows — apps.academics + apps.communication teacher availability guard
- Parent/student portals — apps.portal (existing tenant portal app)
- Academic calendar localization — apps.locale calendar overlays (IN 3-variant per-state + 51-market voice)
- Data quality warnings — apps.migration_cloud visual data cleanup + apps.evals data_quality_warnings
- AI support — apicenter.ai_helpers ONLY; never raw model; baseline 0 enforced

### Homework support guard (anti-cheating)

- Out-of-hours student help — apps.academics.homework_support_guard
- Teacher-configured hint repository — apps.academics.hint_repository per assignment
- Student stuck signal — homework.support_requested event with configured_hint_id_or_null
- Morning teacher insight — apps.evals teacher_morning_insight dashboard
- NO AI hallucinated answer — apicenter rejects unguarded homework completion prompts
- NO cheating/answer leakage — content filter + apps.academics.homework_ai_guardrails

## Repo evidence (anchor paths)

- `apps/academics/`
- `apps/evals/`
- `apps/reports/`
- `apps/student360/`
- `apps/school_events/`
- `apps/dashboard/`
- `apps/locale/`

## Tests

- `apps/academics/tests/test_edos_homework_support_guard_v2.py`
- `apps/evals/tests/test_edos_micro_progress_timeline_v2.py`
- `apps/academics/tests/test_edos_polymorphic_learning_queue.py`

## External blockers (deferred — repo cannot fix)

- live PSP settlement reconciliation per corridor
- SOC2 Type II PDF
- MoE / Ministry of Education per-country live integrations
- WhatsApp Business platform Meta verification
- USSD telecom partner agreements per country
- native push notification wrapper (Capacitor/Tauri) — deferred until first-100-schools proof
- live LiteLLM API keys on Render
- Render SHA parity live verification
- multi-corridor pilot ingestion
- Postgres RLS enforced in production (current local env is SQLite)

## PWA-first posture

PWA is the launch mobile strategy. Native iOS/Android apps are explicitly DEFERRED until web core stability + first-100-schools proof + PWA installability proof. Service worker + manifest + IndexedDB + offline queue shipped in prior batches; this re-architecture preserves and consumes that infrastructure rather than forking.

## Honesty notes

- Repo-scope contracts only — no live vendor integration claims.
- Existing canonical models preserved; metadata layer absorbs tenant variance per architecture correction.
- External blockers listed above remain unchanged by batch 1489.
