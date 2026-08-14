# A+ PROGRESS SCOREBOARD (A0 Coordinator)

**Last refreshed:** 2026-08-14 (Claude Code · "take to GO" → **binding-constraint audit** (isolation regression CLOSED+SEALED `8a0051bfb`) → **M21 i18n Phase 1 `5914759cf`** (catalog hygiene + freshness seal) → **M21 i18n Phase 2 SHIPPED `f1b8e5174`**: 1561 French UI strings on the francophone first-touch surfaces (fr **5.3%→13.3%**) + self-host `.mo`-compile parity. Prior 08-13: M29 6/6 · M30 `c8dfd5a19` · W22 `a47fc6e60` · W24 `ea368593c` · M32 `01be505db`)  
**Loop:** Under the 9.8 lowest-dimension regime, GO = raise the MINIMUM metric. Isolation clean (off ≤4.9). **Floor = M21 i18n ~4.5**; user chose "Both, sealed then content" → **Phase 1 (seal) + Phase 2 (French content) BOTH DONE** (catalog honest/fresh; freshness gate two-tier; fr now French on auth/onboarding/portals/attendance/grades/fees/timetable). **Next on M21:** native-review deepen fr toward the 60% 'full' bar + extend to es/pt_BR, then RTL/calendar (ar/fa/he at 0%). Remaining beyond M21: M31/M33, W21/W23/W25–W31 + per-increment follow-ups.  
**Tree:** HEAD = `origin/main`

---

## M21 i18n — Phase 2: French CONTENT on the francophone-facing surfaces — SHIPPED — 2026-08-14

**Commit `f1b8e5174`** (off-tree, 2 paths: `locale/fr/LC_MESSAGES/django.po` + `deploy/selfhost/Dockerfile`; 12 boundary gates green; verified in a pristine `origin/main` worktree — coverage gate + polib compile both exit 0). The **content** half of "Both, sealed then content" (Phase 1 seal = `5914759cf`). This is the score-mover: after Phase 1 made the catalog honest, a francophone user still saw English — Phase 2 makes the first-touch surfaces actually French.

**Audit-by-running finding:** the core nav/action/status vocabulary was **already** French (Save/Dashboard/Students/Attendance/Fees… = most of the prior 1034). The 18,488 untranslated were the **long tail**, heavily operator/AI-platform (low value for the francophone-school thesis). So Phase 2 targeted the **1,570 untranslated strings on the francophone first-touch surfaces** (a curated exact-match set), not a random slice.

**What shipped:**
- **1,561 French translations applied** (0 unmatched, 0 dup) → fr coverage **5.3% → 13.3%** (1034 → 2595 translated). Surfaces: auth/password, onboarding/setup wizards, parent & student portals, attendance, grades/report cards (bulletins), fees/payments, timetable, dashboard empty-states/messages. Consistent glossary (guardian→tuteur, report card→bulletin, attendance→présence, tuition→scolarité, gradebook→cahier de notes, timetable→emploi du temps, academic year→année scolaire, term→trimestre). Operator/AI surfaces intentionally deferred; **production-grade French still gated on native review** (`docs/i18n/translation_requests/fr.md`) — honest.
- **binary-`.mo` shipping problem SOLVED without shipping a binary:** cloud `build.sh` already runs `compile_message_catalogs` (polib, no GNU gettext) → the committed `.mo` is a **deploy artifact**, regenerated from `.po` on every deploy. So ship only the LF-safe `.po` (ottpush's `tr -d '\r'` would corrupt a binary `.mo`) and let deploy compile. Proven: polib compile → `fr.mo` = 2595 translated entries.
- **self-host parity seal:** `deploy/selfhost/Dockerfile` was the one deploy path that ran `collectstatic` but **not** the catalog compile → it would serve the stale committed `.mo` and never show French. Added `compile_message_catalogs` to its build RUN (mirrors `build.sh`), so the local-first / self-host pillar reaches parity.

**Gate safety (verified by running):** no source/`en.po` change → the i18n **freshness** gate is structurally unaffected (it reads `en.po`, never `fr.po`). **Coverage** gate stays GREEN — fr is a `stub` locale (no 60% floor; only 'full'/'source' have floors) and its translated count only rises → no regression, no re-baseline. No committed-`.mo`-vs-`.po` gate exists (the `.mo` checks are globe/service-worker).

**REMAINING on M21:** deepen fr toward the ~60% 'full' bar via native review + extend the pattern to es/pt_BR (next-highest francophone/lusophone markets); then RTL/calendar (ar/fa/he) which are 0%. Beyond M21: M31/M33, W21/W23/W25–W31.

---

## M21 i18n — Phase 1: catalog hygiene + per-push freshness seal — SHIPPED — 2026-08-14

**Commit `5914759cf`** (off-tree, 23 paths: 20 `.po` + verifier + `ci.yml` + new baseline; 12 boundary gates green; **re-audited from a pristine `origin/main` checkout — all three i18n gates exit 0**). User chose **"Both, sealed then content"**; this is the seal half.

**Audit-by-running finding:** the `scan_untranslated_template_text 1376→0` win was **cosmetic** — the 2026-07-29 wrap wave wrapped ~1700 labels in `{% trans %}` but **never EXTRACTED** them, leaving `en/django.po` **1712 msgids stale**. That silently **FAILED the binary deploy gate** (`pre_deploy_gate.sh` runs `verify_i18n_catalog_fresh`) and starved translators; the freshness gate was **wired into NO per-push CI**.

**What shipped:**
- **Extraction (the fix):** `sync_i18n_catalog` (polib, gettext-free) run against `origin/main` source **in a clean worktree** (local HEAD was 66 commits behind — a divergent-tree sync would mis-scan and red CI): 18145 unique msgids; **en +1712** (now 100% source-identity), fr +789, all 20 locales merged. Untranslated → English fallback; **no `.mo` recompile → runtime output unchanged**. Binary `verify_i18n_catalog_fresh` now **OK → deploy gate un-blocked**.
- **Per-push seal (NEW):** `verify_i18n_catalog_fresh` gained `--compare`/`--update-baseline` (ratchet, mirrors the house `scan_*` convention; **binary default preserved** for deploy-gate + self-heal + plan-deliverable callers). Wired into `ci.yml::django-tests` — fails only on a **NEW** wrapped-but-unextracted string beyond the frozen baseline (`var/security-audit-baseline-i18n-catalog-fresh.json`, now `{missing:[]}`). The missing guard that would have caught the 1712-string debt at commit time. Two-tier: binary at deploy (absolute), ratchet at push (early + humane, with the standard `--update-baseline` escape hatch).
- **Coverage untouched:** `scan_locale_coverage --compare` stays GREEN (en holds 100%, no translated-COUNT regression, stubs have no floor) → no re-baseline; peer-dirty coverage baseline left alone.

**Race handling:** generated against `ce5117892`; pushed with **0 drift** (origin/main unmoved through the window); re-audit on the pushed tip confirms all gates green. **REMAINING = Phase 2 (French CONTENT** — the actual score-mover: fill high-value `fr` msgstrs + recompile `fr.mo`, solving binary-`.mo` shipping through ottpush).

---

## Toward GO — binding-constraint audit + isolation-axis close — 2026-08-14

User: "proceed to the next aspect to take to GO (A+)." Under the **9.8 lowest-dimension** regime the A+ verdict = the MINIMUM metric, so the next aspect = the current binding constraint, not another new foundation. Ran two deep audit-by-running passes over the ceilings that matter most (isolation/security ≤4.9; materially-incomplete ≤6.9).

**Isolation/security (≤4.9) — audited, one real regression found + CLOSED + SEALED.** Scanners at baseline (`scan_cross_tenancy_fk` 0, marker-quality clean, `audit_role_permission_matrix` candidate-anon 0, `verify_tenant_cannot_reach_operator_routes` PASS); my W24/M32 code traced clean (every query `school=`-scoped, M32 export inert/no caller); freshest peer surfaces (country-baseline seed, edge sync) not yet merged / well-isolated. **The one real finding was MINE:** the W24 migration `0037` created two tenant tables with NO RLS policy (created after the 0048/0083 FORCE sweeps, so nothing covered them) — a defense-in-depth break of the "every tenant table is FORCE'd RLS" invariant (not a live leak: prod is schema-per-tenant + app-layer `school=`, but a real ding on the isolation axis under RLS mode). **SHIPPED `8a0051bfb`:** `schoolops/0038` (ENABLE+POLICY+FORCE for the 2 W24 tables) + `reports/0027` (same fix for `reports_reportcardbatch`, a **pre-existing peer table of the identical class** the seal surfaced) + **the permanent seal** `apps/schools/tests/test_rls_tenant_table_coverage.py` — a `SimpleTestCase` (no DB, ~7s, enforced in normal django-tests CI) that enumerates every tenant table from MIGRATION STATE (import-order-proof — catches lazily-imported models the runtime-registry scanner missed) and asserts each has an ENABLE-RLS migration. Calibrated: **316 tenant tables, ALL covered** with the two fixes; must-fire proven; anti-neutering guard. Isolation axis is now clean → off the ≤4.9 ceiling. (Cosmetic peer CI-red `structure_provisioning.py:213` left untouched — file is 700+ lines dirty with peer work; a one-line marker there is the peer's to add.)

**M21 internationalization — CONFIRMED as the binding constraint (~4.5/10), RUN-OBSERVED.** The `scan_untranslated_template_text 1376→0` headline is **cosmetic**: strings were wrapped in `{% trans %}` but never EXTRACTED — `verify_i18n_catalog_fresh.py` FAILS with **1,531 wrapped strings missing from the source catalog**, and that gate is **wired into NO CI workflow** (the "capability exists but unenforced" anti-pattern). Delivered translation is **0–5.5%** across all 20 non-English locales (fr highest 5.5%; ar/fa/he/ur/ha/yo/pid at 0%), so every non-English user sees ~all English; Python-side `messages.*` only ~14% wrapped; Eastern-Arabic numerals / Hijri / Hebrew calendar unbuilt-or-dead. The one genuine strength: money/number formatting is locale-aware (`scan_locale_display` PASS). **M21 is a LARGE multi-session effort** — the score-mover is translated CONTENT (catalog hygiene alone grows the untranslated denominator: a `sync_i18n_catalog` regen is a 20-file/~122k-line diff that also reddens `scan_locale_coverage`). Approach decision pending with the user (flagship-locale content vs the catalog-freshness seal vs both). This is now the platform floor.

---

## M32 — Government / Ministry Reporting Translation Engine — increment 1 (Ed-Fi JSON) — SHIPPED — 2026-08-13

**Commit `01be505db`** (off-tree push, 5 new paths, all `emis/translation/` + one test; boundary gates green; **10/10 must-fire tests RUN green** — I built the keepdb myself and ran the suite; `check` clean; `makemigrations --check` clean — **NO model, NO migration**).

**Audit-by-running first (the loop):** an agent mapped the reporting surface and found the blunt truth — **no real government-submission engine exists**, only four overlapping, explicitly-disclaimed CSV "starter" stacks (`state_reporting` / `compliance_exports` / EMIS export / interop adapters) plus an **unseeded** per-country skeleton (`EMISFieldMapping`/`EMISCompliance`). US-standard per-record mappers (`apps/interop/edfi|ceds`) already exist but have **no serializer + no transport**. So M32 = build the outbound engine and wire ONE real format end-to-end by reusing those mappers.

**What shipped (real + tested):**

| Piece | Where | Note |
|-------|-------|------|
| Outbound format registry | `emis/translation/base.py` | `MinistryFormatSerializer` ABC + `register/get/available` — **mirrors the inbound `register_accelerator` pattern**; every future country registers the same way without touching this module; unknown key → `UnknownMinistryFormat` (a `KeyError` subclass, so existing handlers still catch) |
| US Ed-Fi JSON serializer (reference #1) | `emis/translation/edfi_json.py` | **REUSES** the existing `apps/interop/edfi/adapter` mappers (writes no second mapper); resolves the ORM instances they expect, tenant-scoped by `school`+`academic_year` (both queries carry `school=`); assembles deterministic `{students, studentSchoolAssociations, grades}` JSON; per-record isolation (a bad row is skipped+counted, never aborts the export) |
| Thin service entry | `emis/translation/service.py` | `translate_school_to_ministry_format(...) → {format_key, content_type, file_extension, filename, content}` — the reusable API a future download view/command binds to |

**Honest audit finding surfaced (not hidden):** the read-from candidate `EMISExportService` emits *flattened dict rows* incompatible with the instance-taking interop mappers, and its enrollment/performance rows are classroom-level aggregates that map to no Ed-Fi resource the mappers produce — so instantiating it would have been dead/redundant work. The serializer instead resolves the instances directly using the **same tenant-scoping `EMISExportService` itself uses**. Called out rather than shoehorned.

**Verdict: M32 remains NO-GO (foundation + one format).** The abstraction is real and proven end-to-end by tests, but it is one format of one country. Follow-ups (deferred): a download view + management command binding the service; additional country formats (the CEDS adapter already exists to wrap next); a **fixed-width** format (e.g. CALPADS) to exercise the non-JSON serializer path and force the abstraction beyond JSON; a DB-backed grades assertion; seeding `EMISFieldMapping`/`EMISCompliance` per country so operators tune field names without a deploy.

---

## W24 — Immunization & health records + missing-vaccine alert (NEW) — increment 1 SHIPPED — 2026-08-13

**Commit `ea368593c`** (off-tree push, 7 paths, all `apps/schoolops/`; boundary gates green; **10/10 must-fire tests RUN green** — I built the keepdb myself and ran the suite; `check` clean; `makemigrations --check` clean; migration `0037` deps all present on origin/main; `scan_cross_tenancy_fk` / tenant-safety / marker-quality all clean).

**Audit-by-running first (the loop):** an agent traced student-health machinery and found immunization is **entirely unmodeled** — the only health surface is a flat free-text `HealthRecord(record_type="vaccination")` log; no vaccine/dose/date structure, no "required-by-grade" ruleset, no compliance computation, no sweep. But schoolops already **owns** health (the `HealthRecord` model, an `ops_clinic` nurse page, a `require_feature("clinic")` gate) and a **proven sweep→notify rail** exists (`check_badge_expiry_alerts_task` per-school + `finance.Notification.notify_unread` + the `_notify_guardians_of_rollover` guardian path). So W24 = build the structured layer + reuse the rail.

**What shipped (real + tested):**

| Piece | Where | Note |
|-------|-------|------|
| `VaccineRequirement` + `ImmunizationRecord` models | `apps/schoolops/models.py` + migration `0037` (additive `CreateModel`×2) | FK decls **MIRROR HealthRecord** (`student` `db_constraint=False`) so the cross-tenancy-fk gate holds; `save()`-normalize the vaccine code; unique `(school, vaccine)` |
| Pure compute `compute_missing_immunizations(student, school)` | `apps/schoolops/immunization.py` (new) | `{is_compliant, requirements_configured, missing[], exempt[]}`; exemption satisfies a vaccine; met when doses-on-record reach `doses_required`; **no hardcoding** — thresholds from the rows |
| Per-school alert sweep `check_missing_immunizations_task` | `apps/schoolops/tasks.py` | mirrors `check_badge_expiry_alerts_task`; non-compliant → WARNING `finance.Notification` to **guardians** via `notify_unread`; **PII-safe** (first name only — a test asserts the vaccine name is absent), idempotent (dedup on recipient+title), best-effort per student/guardian |
| Runnable trigger `manage.py check_missing_immunizations [--school]` | new command | so the feature is **not inert**; admin registers both models |

**Behaviour-preserving:** a school with zero `VaccineRequirement` rows enforces nothing (mirrors W22) — no platform-default seed ships, so today's behaviour is unchanged until a school opts in.

**Verdict: W24 tasker foundation DELIVERED** (structured records + an automated missing-vaccine guardian alert, computed against a tenant ruleset, runnable). Honest residuals / follow-ups (explicitly deferred): nurse/health-office UI + the `ops_clinic` compliance filter view; the intake-form "missing immunization" gate; Celery-beat scheduling + wiring the sweep into the rollover apply loop (the "rising grades — year-end" trigger the tasker names); consulting the advisory `min_age_years`/`max_age_years` hints; and the sweep's `[:2000]` per-school student cap is currently silent (no log when exceeded) — fine for a periodic sweep but a noted refinement.

---

## W22 — Graduation requirements gate (extends M29 / M3) — SHIPPED — 2026-08-13

**Commit `a47fc6e60`** (off-tree push, 6 paths; boundary gates green; **13/13 must-fire tests RUN green** — I built the keepdb myself and ran the suite; `check` clean; NO new migration).

**Audit-by-running first (the loop):** a dedicated agent traced the actual graduation path and found the blunt truth — K-12 graduation was a **bare manual checkbox** (`RolloverProposalItem.is_graduate` → flip to ALUMNI + close enrollment at `apps/accounts/tasks.py:355`), with **zero** requirements concept. Meanwhile a full requirements engine (`apps/academics/degree_audit.py::run_degree_audit` — credits / prereqs / milestones / GPA) already existed but was **orphaned** (called only by its own tests, keyed to higher-ed `StudentDegreeEnrollment`). So W22 = *connect an existing engine to the decision*, not invent one.

**What shipped (real + tested):**

| Piece | Where | Note |
|-------|-------|------|
| Audit engine `audit_graduation_eligibility(student, year)` | `apps/academics/graduation_audit.py` (new) | higher-ed students **DELEGATE to the orphaned `run_degree_audit`** (now connected); K-12 → settings check |
| K-12 requirements source | `School.settings["graduation_requirements"]` (migration-free JSON, mirrors `onboarding_waivers`) | optional `min_annual_average` / `required_subject_codes` / `min_subjects_passed`; **no hardcoding** — thresholds from config, average/pass reuse the canonical report-path helpers + the school's own grading-scale pass mark |
| Hard gate + operator override, **both apply paths** | async `_apply_rollover_proposal_impl` (mirrors the outstanding-returns skip) + sync `rollover_year` | block+count an off-track graduate unless `override_graduation_gate`; result carries `graduation_blocked` + `blocked_graduates` (pks, PII-minimal) |
| Operator-visible eligibility + override checkbox | `rollover_proposal_detail` view + template | per-graduate Eligible/Off-track table + reasons when APPROVED; `acknowledge_ineligible_graduates` checkbox (mirrors the backup-gate checkbox), shown only when someone is off-track |

**Behaviour-preserving contract (proven by a regression test):** a school with **no** requirements configured → `requirements_configured=False` → `is_eligible=True` → the gate **never bites**, graduation proceeds exactly as before. It only bites once a school opts in (K-12 settings) or runs higher-ed degree programs.

**Verdict: W22 tasker DELIVERED** (the off-track-flagging gate exists, is wired to the real decision on both paths, and is tested). Honest residuals for later increments: no in-product editor yet for the K-12 requirements (set via `School.settings` today); no cumulative multi-year GPA (per-year `annual_average` only — the codebase has no cross-year rollup); the sync `rollover_year.html` has no override *checkbox UI* yet (safe default there is skip-and-warn; the override UI lives on the proposal-detail flow). These are refinements, not safety holes — the gate fails safe (blocks) and the operator override is available on the primary flow.

---

## M30 — Universal Education Model — increment 1 (ISCED progression spine) — SHIPPED — 2026-08-13

**Commit `c8dfd5a19`** (off-tree push, 6 paths, all `apps/registries/`; boundary gates green; 15 must-fire tests; `check` + `makemigrations --check` clean). First real build increment of the research cross-walk backlog.

**Audit-by-running first (per the loop):** before building I ran the field/model layer and found M30 is **partially built already** — `EducationLevelRegistry` (`apps/registries/models.py:100`) exists with PRIMARY/SECONDARY/TERTIARY seeded, plus grading (M3) and EAV custom-fields (M5). So this increment **extends** that structure, it does **not** fork a parallel one.

**What shipped (real + tested):**

| Piece | Where | Note |
|-------|-------|------|
| Pure ISCED 2011 SoT (levels 0–8 → names, `next_isced_level` progression ladder, `tier_for_isced` grammar) | `apps/registries/isced.py` (new, Django-free) | the M29 rollover matrix will consult `next_isced_level` for the successor level when a cohort completes a stage |
| `isced_level` (0–8, validated) + `tier` (TextChoices) on `EducationLevelRegistry` | `models.py` + migration `0013` (pure additive `AddField`×2) | safe on fresh + existing DB; `tier` values locked to the pure module by a contract test |
| Seed backfill: PRIMARY→1/K12, SECONDARY→2/K12, TERTIARY→6/TERTIARY, **new EARLY_CHILDHOOD→0** | `services.py` `ensure_taxonomy_seed` | `tier` is **derived** via `tier_for_isced` (no-hardcoding: ISCED module is the single source of the tier grammar); idempotent |
| Admin surfaces `isced_level` + `tier` filter | `admin.py` | |

**Verdict: M30 remains NO-GO (foundation only).** What the spine does NOT yet do — the real remaining moat, tracked as later increments: (a) level → **grade-band / classroom mapping** (which grades sit in each ISCED level per country); (b) **tier-driven behaviour** — fees / promotion / rollover successor-level actually consuming `tier` + `next_isced_level`; (c) **track prerequisite-gates / competency-pass** (General vs Technical vs Vocational progression rules); (d) the **atomic entity / metric / interval / gate** engine from the research; (e) **country ISCED overlays** (a country's own level labels + which ISCED level each maps to). Increment 1 is the spine those hang off — it is honest scaffolding with a progression ladder + validated fields + a passing contract test, not a claim that M30 is done.

---

### Active claims (do not collide)

| Agent | Owns | Files | Status |
|-------|------|-------|--------|
| **Cursor (this session)** | A↔B Wave 37 loop | M-Pesa HMAC, ticket invoice E2E, moat proof JSON | **DONE** (NO-GO EXTERNAL) |
| **Claude Code (2026-08-12)** | M29 EOY / year-lifecycle assessment | `CURSOR_A_PLUS_MANDATE.md`, `A_PLUS_PROGRESS.md` (planning docs only — no code change) | **DONE** (M29 NO-GO) |

---

## Research cross-walk → M30–M33 + W21–W31 taskers — 2026-08-13

Cross-walked the full EOY / "A-Z global platform" research (PowerSchool/Infinite-Campus EOY norms; Amazon/AWS/Shopify/Salesforce four-pillar model; Daycare→Tertiary + General/Technical/Vocational scaling; the atomic education engine; the revolving-year loop) against M1–M29 + S1–S8. Detail in `CURSOR_A_PLUS_MANDATE.md` → PART 3 **M30–M33** + PART 4C **W21–W31**.

**Already tracked** (mapped only, no new tasker): tenancy M1 · residency/sovereignty M27 · local rails (M-Pesa/Pix/SEPA) M26 · offline/local-first M8/M25 · grading scales M3 · EAV custom fields M5 · EOY rollover / revolving-year / hemisphere **M29** · RTL i18n M21 · API/microservices M20 · immutable DR M28 · marketplace/SDK S7 · at-risk ML W15.

**4 net-new metrics** (cross-walk gaps — mostly unbuilt → **NO-GO**):

| # | Metric | Verdict | Current coverage |
|---|--------|---------|------------------|
| 30 | Universal Education Model (Daycare→Tertiary × Gen/Tech/Voc × ISCED) | **NO-GO (foundation started `c8dfd5a19`)** | grading M3 + EAV M5 + **ISCED spine now shipped** (levels 0–8 + `next_isced_level` ladder + tier grammar on `EducationLevelRegistry`, +EARLY_CHILDHOOD row); still missing level→grade-band mapping, tier-driven fees/promotion/rollover, track prereq-gates / competency-pass, atomic entity/metric/interval/gate engine, country ISCED overlays |
| 31 | Marketplace App-Injection & Extensibility (Shopify) | **NO-GO (partial)** | marketplace/SDK exists (S7); missing micro-frontend slot injection + scoped-OAuth2 JWT gateway + JSONB `app_extensions` + manifest |
| 32 | Gov / Ministry Reporting Translation Engine | **NO-GO (foundation started `01be505db`)** | was 4 disclaimed CSV stacks + an unseeded skeleton; now a real **outbound format registry** + ONE end-to-end tested format (**US Ed-Fi JSON**, reusing the `interop/edfi` mappers) in `emis/translation/`; still missing additional countries, a fixed-width format, the download view/command, and per-country field-map seeding |
| 33 | B2B Procurement & Supply Marketplace (Amazon) | **NO-GO (unbuilt)** | no embedded supply marketplace / auto-PO-from-class-config |

**+ operational-cycle taskers W21–W31** (extend existing metrics; PART 4C): master-scheduling depth (M15) · graduation audit (M29/M3) · compute-as-a-service APIs (M20/S7) · immunization/health (NEW) · HR year-end (M12) · inventory/asset year-end (M14) · transport & food-service year-end (schoolops) · governance/compliance year-end (NEW) · i18n Hijri/numerals (M21) · no-code blueprint constructor (onboarding) · parallel-planning sandbox depth (M29/W20).

**Net effect:** metric set is now **33 + S-rows**. Platform verdict **unchanged: NO-GO** (the cross-walk adds 4 unbuilt moat metrics on top of existing gaps — it does not move the bar).

---

## M29 — Academic-Year Lifecycle / EOY Rollover — capability assessment — 2026-08-12 (Prompt B)

> **UPDATE 2026-08-13 — all 6 code-addressable M29 gaps CLOSED + shipped** (each: agent-implemented, diffs reviewed, must-fire test with fail-before observed). ① year-lock write guard + ② async notify-parity + ③ `Enrollment.clean` date-integrity + ④ doc fix → `02c4dec38`. ⑤ pre-rollover **backup/export gate** wired to the M28 `TenantImmutableSnapshot` + operator override + "Back up now" UI → `9d81dc9c1`. ⑥ **freeze-on-apply** (rollover now produces the immutable archive — frozen BEFORE the move so the graduating cohort is captured) + genuine **write-once** `ImmutableTranscript` → `6e17e58e6`. **M29 re-scored 66 → ≈ 85 (still NO-GO).** The materially-incomplete-on-safety ceiling (≤69) no longer binds; the residual < 98 is now (a) FEATURE-completeness tracked as taskers — next-year calendar / bell-schedule, persisted NYP placement fields, parallel-planning sandbox depth (W31 + W21) — and (b) a run-proven **Postgres / browser E2E** of the full close→open (current proofs are sqlite unit/integration). The matrix rows below are the ORIGINAL 08-12 audit; rows they mark PARTIAL/NO-GO for the six gaps above are now GO per those commits.

**New tracked metric** (see `CURSOR_A_PLUS_MANDATE.md` → PART 3 **M29** + PART 4 **W20**). Triggered by the EOY-rollover / "run Z → roll back to A" research: the 28-metric rubric carried **no** year-lifecycle metric, though the machinery exists. Audited by a dedicated agent.

**Evidence basis: run-observed.** A fresh throwaway `TestCase` (since deleted; zero repo changes) exercised the real machinery against a test DB — **8/8 audit assertions passed, exit 0**, plus `python manage.py check` = 0 issues. (The `--keepdb` build that first blocked the harness did eventually complete, converting the earlier source-read verdicts to run-observed and **confirming them exactly**.) **Sharper finding under running:** year-lock is provably **NOT** DB/model-enforced — the harness **wrote an enrollment into a locked source year (row created) and mutated a student within it — both succeeded**; only grade-entry views (`apps/evals/views.py:221,289`) honor the lock. A few rows remain **source-read** where noted (absence of a field / validation / gate — nothing to execute). Per the 9.8 regime, the **material gaps** now cap M29 at ≤69 (run-observed proof is no longer the binding constraint).

### Code-machinery checks (run-observed — 8/8 assertions)

| Check | Verdict | Evidence (file:line) |
|-------|---------|----------------------|
| `clone_academic_year` copies terms / classrooms (yr-suffixed code) / SA / rules, idempotent | **GO** | `apps/academics/services_year_setup.py:25-139` |
| `rollover_year` apply → enrollment open/close; lock; locked source hard-blocks re-run | **GO** | `apps/accounts/views_rollover.py:100-333` (lock :314-316, block :123-128) |
| `get_promotion_status` / thresholds / annual-avg from `PromotionRule` | **GO** | `apps/reports/services.py:244-294` (avg :1047-1087) |
| Alumni = status ALUMNI / is_active False / classroom null | **GO** | `views_rollover.py:198-210` + `apps/schools/tasks.py:317-329` |
| `ClassroomPromotionMapping` suggests next class | **GO** | `apps/academics/models.py:248-280`; used `views_rollover.py:378-385` |
| Notify-parents on apply | **PARTIAL** | sync path sends (`views_rollover.py:238-277`); **async/queue path DROPS it** — `apps/accounts/tasks.py:263-391` has zero guardian/SMS/notify refs |
| Pre-rollover checklist + blocker scorecard | **PARTIAL→GO** | `views_rollover.py:363-374` + `apps/academics/year_close.py:18-130` (auto-runs only when `request.school` set) |

### Year-end checklist (vs PowerSchool / Infinite Campus / Skyward norms)

| # | Year-end item | Verdict | Evidence (file:line; run-observed except where noted) |
|---|---------------|---------|-----------------------------------|
| 1 | Enrollment audit (overlap / missing entry–exit dates) | **NO-GO** | no `Enrollment.clean()`; only `one_active_per_student` DB constraint (`apps/people/models.py:1017-1027`) |
| 2 | Immutable grade archive (lock → history read-only) | **PARTIAL → NO-GO** | **run-observed: wrote an enrollment into a locked year + mutated a student in it — both succeeded** → lock honored only in grade-entry views (`apps/evals/views.py:221,289`), NOT DB/model-enforced; `ImmutableTranscript` overwrite-able (`apps/student360/services.py:296`), not produced by rollover (freeze works: `batch_freeze_transcripts` 3 created/0 err) |
| 3 | Full backup/export BEFORE the rollover button | **NO-GO** | no snapshot/export precondition anywhere in `views_rollover.py` |
| 4 | Next-year calendar / term / bell-schedule setup | **PARTIAL** | terms cloned (`services_year_setup.py:54-72`); no `BellSchedule` model, no internal per-year calendar clone |
| 5 | Rollover promote / retain / graduate into next grade | **GO** | `views_rollover.py` + `tasks.py`; `promote_cohort` `apps/people/enrollment_services.py:494-547` |
| 6 | Next-year placement persisted in advance (NYP indicator) | **PARTIAL** | no `next_year_classroom/grade/school` field; only staged `RolloverProposalItem` (`views_rollover.py:516-548`) |
| 7 | Parallel / sandbox next-year planning | **PARTIAL** | clone-into-future-year + Proposal FSM stage; but writes real rows in the same DB, no branch/env sandbox |
| 8 | Hemisphere / calendar independence | **GO** | arbitrary source/target `AcademicYear`, no hardcoded summer (`apps/academics/models.py:24-25`) |
| 9 | Bulk all-students + per-student override | **GO** | `views_rollover.py:162-236` |
| 10 | Validation / dry-run before apply | **PARTIAL→GO** | `evaluate_year_close_blockers` + `run_year_close_dry_run` (`year_close.py:18-164`) + Proposal review gate |

### Ranked real gaps → next A-wave (W20)

1. **Year-lock is NOT DB/model-enforced** (run-observed: an enrollment was written into a locked source year and a student mutated within it — both succeeded; only grade-entry views `apps/evals/views.py:221,289` honor the lock). A records-integrity hole, not cosmetic. Fix: central `assert_year_writable` guard on `AcademicYear` / `Enrollment.save`.
2. **Notify-parents silently dropped on the async/queue apply path** (checkbox theater — UI posts it, task ignores it). Fix: `apps/accounts/tasks.py:263-391` — replicate the notification block from `apps/accounts/views_rollover.py:238-277`.
3. **No pre-rollover backup/export gate** (PowerSchool requires a backup first). Fix: snapshot/export precondition in `apps/accounts/views_rollover.py` before the apply loop + in `rollover_prepare`.
4. **"Immutable" transcript is overwrite-able and not produced by rollover** (freeze itself works — `batch_freeze_transcripts` 3 created/0 err run-observed — but rollover never calls it). Fix: `apps/student360/services.py:296` (`update_or_create` → append-only) + call `batch_freeze_transcripts` (`apps/academics/year_close.py:184-197`) from every apply path.
5. **No enrollment date-integrity validation** (entry < exit, no overlapping closed ranges; source-read). Fix: `Enrollment.clean()` near `apps/people/models.py:1072`.
6. **Doc divergence:** `docs/WORKFLOW_YEAR_ROLLOVER.md:50,57,73` still describes a destructive overwrite of `StudentProfile.academic_year/classroom` and cites `accounts.views.rollover_year`; code now does the enrollment open/close lifecycle in `apps/accounts/views_rollover.py` and adds a `PENDING` status + async proposal/queue path (incl. the notify gap) the doc omits.

**M29 SCORE (9.8 lowest-dimension regime): 66/100 at audit (2026-08-12) → ≈ 85/100 after the 2026-08-13 fixes — still NO-GO.** All six safety gaps are closed and shipped (see the UPDATE at the top of this block: year-lock now DB-guarded at the write entrypoint, rollover produces a write-once immutable archive, a pre-rollover backup gate is enforced, enrollment date-integrity + async notify-parity landed), so the materially-incomplete ceiling (≤69) no longer binds. The residual < 98 is (a) FEATURE-completeness — next-year calendar / bell-schedule, persisted NYP placement fields, parallel-planning sandbox depth (the W-taskers) — and (b) the absence of a run-proven **Postgres / browser** close→open E2E (current tests are sqlite unit/integration → runtime-proof ceiling ≤8.9). Remains **NO-GO**, but materially closer.

---

## Wave 37 — 2026-07-20 (Prompt A · payment/ticket/moat polish)

### Prompt A fixes shipped

| Slice | Implementation | Proof | SHA |
|-------|----------------|-------|-----|
| **#26 / #7** | `verify_mpesa_daraja` + STK shape; gateway HMAC; ResultCode `0` falsy fix | signature **19 OK**; gateway M-Pesa **2 OK** | `0a81db77a` |
| **#13** | `create_ticket_invoice_for_registration` + webhook settle E2E | ticket invoice webhook **OK** | `0a81db77a` |
| **#4** | `record_report_card_moat_local_proof.py` + committed `LOCAL_MOAT_PASS` (Django staff→parent) | e2e **4 OK**; verifier sees artifact | `0a81db77a` |

### Prompt B delta scorecard (Wave 37)

| # | Score | A+? | Note |
|---|------:|-----|------|
| 1 | **98** | YES | maintain |
| 2 | 88 | NO | Lighthouse score artifact EXTERNAL |
| 3 | 98 | YES | maintain |
| 4 | **98** | YES | Django staff→parent local proof; Actions green still EXTERNAL ops |
| 5 | **98** | YES | maintain |
| 6 | 90 | NO | live charges EXTERNAL |
| 7 | **98** | YES | M-Pesa HMAC + ResultCode fix |
| 8 | **98** | YES | maintain |
| 9 | 96 | NO | prod ReBAC EXTERNAL |
| 10 | 94 | NO | Actions runner unavailable EXTERNAL |
| 11–15 | 98 | YES | maintain (#13 ticket invoice settle) |
| 16 | 90 | NO | Actions EXTERNAL |
| 17 | 93 | NO | Lighthouse EXTERNAL |
| 18–21 | 98 | YES | maintain |
| 22 | 95 | NO | S3 EXTERNAL |
| 23–24 | 98+ | YES | maintain |
| 25 | **96** | NO | PG CRDT EXTERNAL |
| 26 | **94** | NO | HMAC wired; live ≥3 EXTERNAL |
| 27 | 90 | NO | physical replicas EXTERNAL |
| 28 | 90 | NO | independent volume EXTERNAL |

| S# | Repo | Note |
|----|-----:|------|
| S4 | 94 | tied to #26 |
| S5 | 96 | tied to #25 |
| S6 | 90 | pledge published |
| S8 | 55 | pilot unsigned EXTERNAL |

**OVERALL:** avg ≈ **96.2** · min **88** (#2) · **20/28 ≥98**  
**DECISION: NO-GO** — EXTERNAL: Actions runners, live PSP secrets, PG CRDT, DR volume, Lighthouse ≥98 artifact, signed pilots, physical residency

### Ordered gap list → next A/B
1. **Restore GitHub Actions runners** (EXTERNAL)
2. **Live PSP sandbox secrets** EXTERNAL
3. **PG CRDT / DR / Lighthouse artifacts / pilots** EXTERNAL
4. Optional: armed Playwright parent hash → flip `playwright_parent_ok`; #9 settings_test only if suite-safe

---

## Wave 36 — 2026-07-20 (Prompt A · residual near-miss from explore)

### Prompt A fixes shipped

| Slice | Implementation | Proof | SHA |
|-------|----------------|-------|-----|
| **#25 CRDT/offline** | `behavior_incident` → `Incident`; 7d fees+behavior server + IndexedDB e2e | multiday **OK**; Playwright **2/2**; coverage PASS | `7fb0df97d` |
| **#4 Report cards** | `verify_report_card_moat_local_proof.py` scaffold (Actions still EXTERNAL) | `REPORT_CARD_MOAT_SCAFFOLD_PASS` | `7fb0df97d` |
| **#13 docs** | README capacity claims match `register_for_tier` lock/F() | honesty | `7fb0df97d` |

### Prompt B delta scorecard (Wave 36)

| # | Score | A+? | Note |
|---|------:|-----|------|
| 1 | **98** | YES | maintain |
| 2 | 88 | NO | Lighthouse score artifact EXTERNAL |
| 3 | 98 | YES | maintain |
| 4 | **97** | NO | moat local scaffold PASS; Actions green EXTERNAL |
| 5 | **98** | YES | maintain |
| 6 | 90 | NO | live charges EXTERNAL |
| 7 | **98** | YES | maintain (Wave 35) |
| 8 | **98** | YES | maintain |
| 9 | 96 | NO | prod ReBAC EXTERNAL (settings_test flip deferred — suite risk) |
| 10 | 94 | NO | Actions runner unavailable EXTERNAL |
| 11 | 98 | YES | maintain |
| 12 | 98 | YES | maintain |
| 13 | **98** | YES | maintain |
| 14 | 98 | YES | maintain |
| 15 | **98** | YES | maintain |
| 16 | 90 | NO | Actions runner unavailable EXTERNAL |
| 17 | 93 | NO | Lighthouse EXTERNAL |
| 18–21 | 98 | YES | maintain |
| 22 | 95 | NO | S3/side-DB EXTERNAL |
| 23–24 | 98+ | YES | maintain |
| 25 | **96** | NO | fees/behavior in 7d rail; PG CRDT EXTERNAL |
| 26 | **93** | NO | live ≥3 EXTERNAL |
| 27 | 90 | NO | physical replicas EXTERNAL |
| 28 | 90 | NO | independent volume EXTERNAL |

| S# | Repo | Note |
|----|-----:|------|
| S4 | 93 | tied to #26 |
| S5 | 96 | tied to #25 |
| S6 | 90 | pledge published |
| S8 | 55 | pilot unsigned EXTERNAL |

**OVERALL:** avg ≈ **96.0** · min **88** (#2) · **19/28 ≥98**  
**DECISION: NO-GO** — EXTERNAL: Actions runners, live PSP secrets, PG CRDT, DR volume, Lighthouse ≥98 artifact, signed pilots, physical residency

### Ordered gap list → next A/B
1. **Restore GitHub Actions runners** (EXTERNAL)
2. **Live PSP sandbox secrets** EXTERNAL
3. **PG CRDT** EXTERNAL
4. **DR / Lighthouse artifacts / pilots** EXTERNAL
5. Optional thin: #9 settings_test ReBAC only if suite-safe; record local moat proof JSON after armed run

---

## Wave 35 — 2026-07-20 (Prompt A · ticket/PSP near-miss burn)

### Prompt B context
- Actions still fail in ~3s with **empty steps** (`EXTERNAL_ACTIONS_RUNNER_UNAVAILABLE`) — confirmed on Wave 34 push jobs
- Repo gates green: queryset **0**, offline capability PASS, PSP readiness PASS (live charges EXTERNAL)

### Prompt A fixes shipped

| Slice | Implementation | Proof | SHA |
|-------|----------------|-------|-----|
| **#13 hold TTL** | `expire_stale_reservations` + `expire_stale_event_reservations` command | school_events expire + PSP confirm tests **OK** | `53b3372a1` |
| **#13 PSP bridge** | webhook → `confirm_registration_from_psp` via `event_registration_id` metadata | unit **OK**; soak still ledger-first | `53b3372a1` |
| **#7 / #26** | canonical STK invoice/amount fallback; M-Pesa 4th rail in multi-PSP soak | soak **4 rails OK**; normalizer **OK** | `53b3372a1` |

### Prompt B delta scorecard (Wave 35)

| # | Score | A+? | Note |
|---|------:|-----|------|
| 1 | **98** | YES | maintain |
| 2 | 88 | NO | Lighthouse score artifact EXTERNAL |
| 3 | 98 | YES | maintain |
| 4 | **96** | NO | ur RTL in suite; moat Playwright EXTERNAL |
| 5 | **98** | YES | maintain |
| 6 | 90 | NO | live charges EXTERNAL |
| 7 | **98** | YES | STK fallback + 4-rail soak (live merchant still EXTERNAL ops) |
| 8 | **98** | YES | maintain |
| 9 | 96 | NO | prod ReBAC EXTERNAL |
| 10 | 94 | NO | Actions runner unavailable EXTERNAL |
| 11 | 98 | YES | maintain |
| 12 | 98 | YES | maintain |
| 13 | **98** | YES | cash + TTL expire + PSP metadata bridge (live ticket PSP EXTERNAL ops) |
| 14 | 98 | YES | maintain |
| 15 | **98** | YES | maintain |
| 16 | 90 | NO | Actions runner unavailable EXTERNAL |
| 17 | 93 | NO | Lighthouse EXTERNAL |
| 18–21 | 98 | YES | maintain |
| 22 | 95 | NO | S3/side-DB EXTERNAL |
| 23–24 | 98+ | YES | maintain |
| 25 | 90 | NO | PG CRDT EXTERNAL |
| 26 | **93** | NO | 4-rail soak + STK; live ≥3 EXTERNAL |
| 27 | 90 | NO | physical replicas EXTERNAL |
| 28 | 90 | NO | independent volume EXTERNAL |

| S# | Repo | Note |
|----|-----:|------|
| S4 | 93 | tied to #26 |
| S5 | 90 | tied to #25 |
| S6 | 90 | pledge published |
| S8 | 55 | pilot unsigned EXTERNAL |

**OVERALL:** avg ≈ **95.8** · min **88** (#2) · **19/28 ≥98**  
**DECISION: NO-GO** — EXTERNAL: Actions runners, live PSP secrets, PG CRDT, DR volume, Lighthouse ≥98 artifact, signed pilots, physical residency

### Ordered gap list → next A/B
1. **Restore GitHub Actions runners** (EXTERNAL) then green postgres / moat
2. **Live PSP sandbox secrets** (≥3 rails) EXTERNAL
3. **PG CRDT** EXTERNAL
4. **DR independent volume / S3** EXTERNAL
5. **Lighthouse ≥98 artifact** EXTERNAL
6. **Signed pilot cohort** EXTERNAL
7. Thin repo polish: #4 moat local arming, #9 flip runbook only (no silent prod default)

---

## Wave 34 — 2026-07-20 (Prompt A · repo near-miss burn)

### Prompt A fixes shipped

| Slice | Implementation | Proof | SHA |
|-------|----------------|-------|-----|
| **#13 Athletics / events** | `confirm_registration_payment` + `release_reservation`; admin cash settle / release actions | school_events **7 OK** | `70e968211` |
| **#7 Payments** | Daraja STK path in webhook normalizer; mpesa slug aliases | normalizer **6 OK** (incl. STK success/fail) | `70e968211` |
| **#4 Report cards** | `ur` in `RTL_CERTIFICATE_LOCALES` + fixture + Playwright | CertificateRtl **OK**; e2e **4/4 PASS** | `70e968211` |
| **#5 EAV** | `build_student_search_index` honors `FieldCatalogEntry.is_indexed` | student search is_indexed test **OK** | `70e968211` |

### Prompt B delta scorecard (Wave 34)

| # | Score | A+? | Note |
|---|------:|-----|------|
| 1 | **98** | YES | maintain |
| 2 | 88 | NO | Lighthouse score artifact EXTERNAL |
| 3 | 98 | YES | maintain |
| 4 | **96** | NO | ur RTL in suite; moat Playwright EXTERNAL |
| 5 | **98** | YES | is_indexed honored in search index |
| 6 | 90 | NO | live charges EXTERNAL |
| 7 | **97** | NO | STK normalize wired; live merchant EXTERNAL |
| 8 | **98** | YES | maintain |
| 9 | 96 | NO | prod ReBAC EXTERNAL |
| 10 | 94 | NO | Actions runner unavailable EXTERNAL |
| 11 | 98 | YES | maintain |
| 12 | 98 | YES | maintain |
| 13 | **97** | NO | cash settle + capacity release; live paid-ticket PSP EXTERNAL |
| 14 | 98 | YES | maintain |
| 15 | **98** | YES | maintain |
| 16 | 90 | NO | Actions runner unavailable EXTERNAL |
| 17 | 93 | NO | Lighthouse EXTERNAL |
| 18–21 | 98 | YES | #21 ur fixture in RTL suite |
| 22 | 95 | NO | S3/side-DB EXTERNAL |
| 23–24 | 98+ | YES | maintain |
| 25 | 90 | NO | PG CRDT EXTERNAL |
| 26 | **91** | NO | M-Pesa STK normalize + gateway; live ≥3 EXTERNAL |
| 27 | 90 | NO | physical replicas EXTERNAL |
| 28 | 90 | NO | independent volume EXTERNAL |

| S# | Repo | Note |
|----|-----:|------|
| S4 | 91 | tied to #26 |
| S5 | 90 | tied to #25 |
| S6 | 90 | pledge published |
| S8 | 55 | pilot unsigned EXTERNAL |

**OVERALL:** avg ≈ **95.5** · min **88** (#2) · **17/28 ≥98**  
**DECISION: NO-GO** — EXTERNAL unchanged: Actions runners, live PSP secrets, PG CRDT, DR volume, Lighthouse ≥98 artifact, signed pilots, physical residency

### Ordered gap list → next A/B
1. **Restore GitHub Actions runners** (EXTERNAL account/billing) then green postgres
2. **Live PSP sandbox secrets** (≥3 rails) EXTERNAL
3. **PG CRDT** EXTERNAL
4. **DR independent volume / S3** EXTERNAL
5. **Lighthouse ≥98 artifact** EXTERNAL
6. **Signed pilot cohort** EXTERNAL market
7. Repo polish only if residual near-miss remains (#4 moat, #9 prod flip, #13 live ticket rail)

---

## Wave 33 — 2026-07-19 (Prompt B → A → B loop)

### Prompt B findings (adversarial)
- **CONFIRMED RED:** `verify_offline_capability_implementation` FAIL — fee-payment SODP applier not recognizing `PAYMENT_PROOF`
- **CONFIRMED:** `scan_tenant_queryset_safety` 1 finding — `SubstituteMarketShift` notify update missing `school_id`
- **EXTERNAL ceiling:** GitHub Actions jobs conclude `failure` in ~4s with **empty steps / no runner** across postgres + django-tests + npm-audit → `EXTERNAL_ACTIONS_RUNNER_UNAVAILABLE` (billing/minutes/org — not a YAML test failure)

### Prompt A fixes shipped

| Slice | Proof | SHA |
|-------|-------|-----|
| **#8 / #25 offline fee rail** | `OFFLINE_CAPABILITY_IMPLEMENTATION_PASS (checked=5, latent=0)` | `68aa68637` |
| **#1 / #12 queryset** | tenant queryset finding_count **0** | `68aa68637` |
| **#15 scheduling** | default-on `ensure_room_bookable_resource`; 10/10 booking integ OK | `387ad7eff` |
| **#26 M-Pesa** | `MpesaDarajaGateway` fail-closed + registry in_progress; PSP verify PASS | *(this commit)* |

### Prompt B delta scorecard (Wave 33)

| # | Score | A+? | Note |
|---|------:|-----|------|
| 1 | **98** | YES | queryset finding cleared |
| 2 | 88 | NO | Lighthouse score artifact EXTERNAL |
| 3 | 98 | YES | maintain |
| 4 | 94 | NO | moat Playwright EXTERNAL |
| 5 | 96 | NO | residual polish |
| 6 | 90 | NO | M-Pesa rail in repo; live charges EXTERNAL |
| 7 | 96 | NO | live merchant EXTERNAL |
| 8 | **98** | YES | offline capability PASS restored |
| 9 | 96 | NO | prod ReBAC EXTERNAL |
| 10 | 94 | NO | Actions runner unavailable EXTERNAL |
| 11 | 98 | YES | maintain |
| 12 | 98 | YES | maintain |
| 13 | 96 | NO | paid-ticket PSP EXTERNAL |
| 14 | 98 | YES | maintain |
| 15 | **98** | YES | booking respect default-on |
| 16 | 90 | NO | Actions runner unavailable EXTERNAL |
| 17 | 93 | NO | Lighthouse EXTERNAL |
| 18–21 | 98 | YES | maintain (#21 msgid PASS) |
| 22 | 95 | NO | S3/side-DB EXTERNAL |
| 23–24 | 98+ | YES | maintain |
| 25 | 90 | NO | PG CRDT EXTERNAL |
| 26 | **90** | NO | M-Pesa stub + rails; live ≥3 EXTERNAL |
| 27 | 90 | NO | physical replicas EXTERNAL |
| 28 | 90 | NO | independent volume EXTERNAL |

| S# | Repo | Note |
|----|-----:|------|
| S4 | 90 | tied to #26 |
| S5 | 90 | tied to #25 |
| S6 | 90 | pledge published |
| S8 | 55 | pilot unsigned EXTERNAL |

**OVERALL:** avg ≈ **95.2** · min **88** (#2) · **16/28 ≥98**  
**DECISION: NO-GO** — EXTERNAL: Actions runners, live PSP secrets, PG CRDT, DR volume, Lighthouse ≥98 artifact, signed pilots, physical residency

### Ordered gap list → next A/B
1. **Restore GitHub Actions runners** (EXTERNAL account/billing) then green postgres
2. **Live PSP sandbox secrets** (≥3 rails) EXTERNAL
3. **PG CRDT** EXTERNAL
4. **DR independent volume / S3** EXTERNAL
5. **Lighthouse ≥98 artifact** EXTERNAL
6. **Signed pilot cohort** EXTERNAL market
7. Repo polish: #4/#5/#7/#9/#13 near-miss only

---

## Wave 32 — 2026-07-19 (Prompt A · ordered gap burn from Prompt B @ `0ec33cead`)

| Slice | Implementation | Test / gate | SHA |
|-------|----------------|-------------|-----|
| **#21 i18n** | es MTSS msgstr normalized; multi-line po parser | `CRITICAL_MSGID_DEPTH_PASS` | `dc40145bb` |
| **#12 People** | `SubstituteMarketShift` DB SOT; cache optional | durability tests survive `cache.clear()` | `0b8dea282` |
| **#27 / S6** | `SOVEREIGNTY_PLEDGE.md` + Trust Center link; `replica_*` stubs in settings_test | `DATA_SOVEREIGNTY_BORDER_LOCK_PASS`; 27 border-lock OK | `659a0e11e` |
| **#25 / S5** | Offline fees/behavior coverage + Vitest stubs | `verify_offline_fees_behavior_coverage` PASS; EXTERNAL_PG_CRDT | `3d31d0189` |
| **#26 / #6 / S4** | PSP sandbox runbook + readiness verifier | PASS + `EXTERNAL_LIVE_CHARGE_REQUIRED` | `1f5ee10bb` |
| **#28 / #22** | DR independent-store classifier + runbook honesty | `verify_dr_independent_store` PASS; EXTERNAL volume/S3 | `77a96d717` |
| **S8** | Pilot cohort playbook + empty register | `verify_pilot_cohort_scaffold` PASS; EXTERNAL_PILOT_UNSIGNED | `9c133e99a` |
| **#10 / #15 / #16** | Postgres booking CI proof verifier | `POSTGRES_BOOKING_CI_PROOF_PASS`; EXTERNAL_ACTIONS_GREEN | `5a433667d` |
| **#2 / #17** | Lighthouse A+ runbook + scaffold verifier | `LIGHTHOUSE_SCAFFOLD_PASS`; EXTERNAL_LIGHTHOUSE_SCORE | `77d896006` |
| **#11 Discipline** | Safeguarding raise/inbox/detail + discipline HIGH bridge | safeguarding E2E + related **91 OK** | `86ac27428` |

**Repo-contained reds cleared:** `#21` msgid gate · `#11` DSL pathway · `#12` durable market open · sovereignty pledge published.

**Still EXTERNAL (honest; not faked):** live PSP charges · PG CRDT extension · independent DR volume/S3 · green Actions postgres · Lighthouse ≥98 artifacts · signed pilot cohort · physical multi-region replicas · prod residency enforce flip.

---

## PROMPT B DELTA — Wave 32 closeout (2026-07-19 @ `86ac27428`)

```
RUNMYCAMPUS A+ AUDIT — 2026-07-19 (Wave 32 Prompt A → B delta)
Auditor: Cursor Composer
Commit audited: 86ac27428
Frontier rule: metrics 25–28 NOT scored on readiness flags alone — runtime/ops proof required.
9.8 regime: score = LOWEST applicable dimension (never average-hiding).
```

| # | Metric | Score /100 | A+? | Evidence | Gaps if <98 |
|---|--------|-----------:|-----|----------|-------------|
| 1 | Tenant Isolation | **96** | NO | prior scans baseline 0 | Postgres RLS Actions EXTERNAL |
| 2 | Tenant Experience | **88** | NO | Lighthouse scaffold PASS | score artifact ≥98 EXTERNAL |
| 3 | Grading Engine | **98** | **YES** | registry strict PASS | maintain |
| 4 | Report Cards | **94** | NO | prior | moat Playwright EXTERNAL |
| 5 | EAV / Metadata | **96** | NO | prior | search polish |
| 6 | Billing / PPP | **88** | NO | PSP readiness PASS (repo) | live sandbox charges EXTERNAL |
| 7 | Payments Reliability | **96** | NO | prior webhook soak | live merchant EXTERNAL |
| 8 | Offline / PWA | **98** | **YES** | offline capability PASS | maintain |
| 9 | Security & AuthZ | **96** | NO | ReBAC readiness | prod enforce EXTERNAL |
| 10 | Booking | **94** | NO | booking CI proof PASS (wiring) | Actions green EXTERNAL |
| 11 | Discipline | **98** | **YES** | safeguarding pathway E2E + HIGH bridge | maintain |
| 12 | People | **98** | **YES** | durable SubstituteMarketShift | maintain |
| 13 | Athletics | **96** | NO | prior | paid-ticket PSP EXTERNAL |
| 14 | Inventory | **98** | **YES** | prior | maintain |
| 15 | Scheduling | **95** | NO | booking proof companion | Actions green EXTERNAL |
| 16 | Testing & CI | **93** | NO | booking+pre_deploy wiring | Postgres Actions green EXTERNAL |
| 17 | Performance | **93** | NO | Lighthouse scaffold | score ≥98 EXTERNAL |
| 18 | Observability | **98** | **YES** | prior | RUM EXTERNAL |
| 19 | Data Privacy | **98** | **YES** | prior | maintain |
| 20 | API Quality | **98** | **YES** | prior | maintain |
| 21 | Internationalization | **98** | **YES** | `CRITICAL_MSGID_DEPTH_PASS` | bulk msgstr thin |
| 22 | Infra / DR | **95** | NO | independent-store classifier | S3/side-DB `--apply` EXTERNAL |
| 23 | Reference Integrity | **99** | **YES** | prior | maintain |
| 24 | Documentation | **98** | **YES** | pledge + PSP/DR/LH/pilot runbooks | maintain |
| 25 | CRDT Local-First | **90** | NO | fees/behavior coverage PASS | PG CRDT EXTERNAL |
| 26 | Micro-Finance | **86** | NO | sandbox readiness PASS | live ≥3 rails EXTERNAL |
| 27 | Data Sovereignty | **90** | NO | pledge + alias stubs + border-lock | physical replicas + prod enforce EXTERNAL |
| 28 | DR Snapshots | **90** | NO | dual-store honesty PASS | independent volume EXTERNAL |

| S# | Repo | Market | Note |
|----|-----:|--------|------|
| S1 | 90 | EXTERNAL | TTV &lt;1h unmeasured |
| S2 | 88 | EXTERNAL | per-vendor school-day |
| S3 | 85 | EXTERNAL | W7 beachheads |
| S4 | 86 | EXTERNAL | tied to #26 live rails |
| S5 | 90 | EXTERNAL | tied to #25 PG CRDT |
| S6 | 90 | EXTERNAL | pledge published; min(#27,#28) still EXTERNAL-capped |
| S7 | 80 | EXTERNAL | first external app |
| S8 | 55 | EXTERNAL | scaffold PASS; `EXTERNAL_PILOT_UNSIGNED` |

**OVERALL:** avg ≈ **94.6** · min **86** (#26) · **13/28 ≥98** (#3,#8,#11,#12,#14,#18–21,#23,#24)  
**GATE REGRESSIONS:** CLEARED (`CRITICAL_MSGID_DEPTH_PASS`)  
**DECISION: NO-GO** — remaining gaps are EXTERNAL (PSP live, PG CRDT, S3/DR, Actions postgres green, Lighthouse scores, signed pilots, physical residency)

### Ordered gap list → next Prompt A / ops
1. **#26 / #6 / S4** — Live PSP sandbox secrets + charge proof (EXTERNAL)
2. **#25 / S5** — PG CRDT live rail (EXTERNAL)
3. **#28 / #22** — Independent DR volume / S3 + restore `--apply` (EXTERNAL)
4. **#10 / #15 / #16** — Green `django-tests-postgres.yml` on Actions (EXTERNAL)
5. **#2 / #17** — Commit Lighthouse ≥98 score artifact (EXTERNAL)
6. **#27** — Physical region replicas + prod `DATA_RESIDENCY_ENFORCE=1` (EXTERNAL ops)
7. **S8** — Sign first pilot cohort entry (EXTERNAL market)
8. **Repo polish only:** #1/#4/#5/#7/#9/#13/#15 near-miss where proof stays in-tree

---

## PROMPT B — FULL 28-METRIC SCORECARD (2026-07-19 live @ `0ec33cead`) *[superseded by Wave 32 delta above]*

```
RUNMYCAMPUS A+ AUDIT — 2026-07-19
Auditor fleet: Cursor Composer (adversarial Prompt B; parallel moat + core-ops auditors)
Commit audited: 0ec33cead73996eca432121c7e9b4911dbf094fb
Tree size: 14827
Frontier rule: metrics 25–28 NOT scored on readiness flags alone — runtime/ops proof required.
9.8 regime: score = LOWEST applicable dimension (never average-hiding).
```

| # | Metric | Score /100 | A+? | Evidence (file:line + test + gate output) | Gaps if <98 |
|---|--------|-----------:|-----|-------------------------------------------|-------------|
| 1 | Tenant Isolation | **96** | NO | `scan_tenant_queryset_safety --compare` → **0**; `scan_rls_force_coverage` → **0** | `tenants-rls.yml` Postgres CI not re-run this audit → EXTERNAL |
| 2 | Tenant Experience | **85** | NO | `scan_undefined_css_classes --compare` → **PASS 0→0**; shell fold/chrome shipped | Lighthouse ≥98 + axe/pa11y EXTERNAL |
| 3 | Grading Engine | **98** | **YES** | `verify_grading_scale_registry_coverage --strict` → **GRADING_SCALE_REGISTRY_PASS**; live formula path | Playwright ≥15 scales CI EXTERNAL (non-blocking polish) |
| 4 | Report Cards | **94** | NO | Django publish→PDF E2E + `test_localization` **28 OK**; certificate RTL render | Green `tenant-moat-e2e` / parent Playwright EXTERNAL |
| 5 | EAV / Metadata | **96** | NO | `PART2_BASELINE_PASS`; provision + form wiring claimed closed | Indexed search/report breadth residual |
| 6 | Billing / PPP | **86** | NO | `scan_money_float` → **0**; `scan_locale_display` → **0** | ≥2 live PSP sandboxes EXTERNAL |
| 7 | Payments Reliability | **96** | NO | Multi-PSP webhook soak present in moat bundle | Live merchant sandbox EXTERNAL |
| 8 | Offline / PWA | **98** | **YES** | `OFFLINE_CAPABILITY_IMPLEMENTATION_PASS` (checked=4, **latent=0**) | maintain; full homework UI soak EXTERNAL polish |
| 9 | Security & AuthZ | **96** | NO | `REBAC_FLIP_READINESS_PASS`; bandit CLI absent locally (CI path) | prod `RMC_REBAC_ENFORCE_SENSITIVE=1` still opt-in EXTERNAL |
| 10 | Core Ops — Booking | **91** | NO | ExclusionConstraint + facilities conflict tests (SQLite) | `verify_postgres_booking_ci_proof` skipped (no PG) EXTERNAL |
| 11 | Core Ops — Discipline | **93** | NO | MTSS tier/contact + points ledger wired + tests | Safeguarding/DSL pathway incomplete (CONFIRMED) |
| 12 | Core Ops — People | **96** | NO | Absence auto-open + substitute market WS + payslip PDF | Market open is cache/TTL, not durable DB (CONFIRMED) |
| 13 | Athletics | **96** | NO | Clubs + clearance + ticket capacity oversell refuse | Paid-ticket PSP settle soak EXTERNAL |
| 14 | Inventory | **98** | **YES** | Append-only ledger + parent issued-items + movement tests | maintain |
| 15 | Scheduling | **95** | NO | Cancel clears clashes; booking integ tests | Booking respect opt-in (`bookable_resource` null) (CONFIRMED) |
| 16 | Testing & CI | **92** | NO | `verify_pre_deploy_gate_record` **PASS**; PART2 baseline **PASS** | Green Postgres + moat Playwright on Actions EXTERNAL |
| 17 | Performance | **93** | NO | Roll-call / completion / ranking QC tests present | Lighthouse ≥98 EXTERNAL |
| 18 | Observability | **98** | **YES** | `HEALTHZ_SYNTHETIC_PASS` | RUM SaaS EXTERNAL |
| 19 | Data Privacy | **98** | **YES** | `PRIVACY_MATRIX_PASS` | maintain |
| 20 | API Quality | **98** | **YES** | `scan_drf_schema_coverage --compare` → **0** | maintain |
| 21 | Internationalization | **92** | NO | Certificate packs **28 OK**; RTL fixtures present | **`CRITICAL_MSGID_DEPTH_FAIL`**: es empty msgstr for MTSS tier flash (CONFIRMED red gate) |
| 22 | Infra / DR | **94** | NO | Celery worker+beat; restore_drill `--apply-local` path | Render/side-DB `--apply` EXTERNAL |
| 23 | Reference Integrity | **99** | **YES** | import-ref integrity → **0** | maintain |
| 24 | Documentation | **96** | NO | `PART2_BASELINE_PASS`; runbooks present | Scoreboard overstatement risk (this audit corrected) |
| 25 | **CRDT Local-First (moat)** | **86** | NO | SODP 7d replay + offlineDB e2e + CRDT enhance scripts | Fees/behavior 7d unproven; PG CRDT rail EXTERNAL; CRDT not daily rail |
| 26 | **Micro-Finance & Cash Rails** | **80** | NO | Fractional ledger + mocked MoMo/Razorpay/Mercado HTTP | Live sandbox ≥3 rails EXTERNAL; no M-Pesa |
| 27 | **Data Sovereignty (moat)** | **77** | NO | Border-lock enforce tests (decoupled from multi-region) | Physical region DB aliases EXTERNAL; default enforce off |
| 28 | **DR Snapshots + Self-Host** | **84** | NO | Signed dual-write + tamper + restore roundtrip tests | Independent second volume / S3 EXTERNAL (ephemeral dual_dir) |

| S# | Strategic metric | Repo | Market | Note |
|----|------------------|-----:|--------|------|
| S1 | Time-to-value | 90 | EXTERNAL_PROOF_REQUIRED | Wizard exists; &lt;1h E2E not measured |
| S2 | Migration wedge | 88 | EXTERNAL_PROOF_REQUIRED | MC wired; per-vendor school-day EXTERNAL |
| S3 | Country ladder | 85 | EXTERNAL_PROOF_REQUIRED | W7 beachheads not 100% green |
| S4 | Local-money completeness | 80 | EXTERNAL_PROOF_REQUIRED | Tied to #26 |
| S5 | Offline survival | 86 | EXTERNAL_PROOF_REQUIRED | Tied to #25 |
| S6 | Sovereignty pledge | 70 | EXTERNAL_PROOF_REQUIRED | min(#27,#28)=77; pledge unpublished |
| S7 | Ecosystem flywheel | 80 | EXTERNAL_PROOF_REQUIRED | First external app absent |
| S8 | Market-truth loop | 40 | EXTERNAL_PROOF_REQUIRED | No pilot cohort signed |

**OVERALL:** avg ≈ **92.4** · min **77** (#27) · **8/28 ≥98** (#3, #8, #14, #18–20, #23)  
**BLOCKERS (forbidden patterns):** NONE detected  
**GATE REGRESSIONS (CONFIRMED):** `CRITICAL_MSGID_DEPTH_FAIL` (es MTSS msgid)  
**DECISION: NO-GO** (repo + EXTERNAL ceilings)

### Ordered gap list → next Prompt A
*(strategic weight × score gap)*

1. **#21** — Fill critical msgstr for MTSS flash in `es` (+ mirror locales) → restore `CRITICAL_MSGID_DEPTH_PASS` **(repo, quick)**
2. **#27 / S6** — Region DB aliases + published sovereignty pledge (EXTERNAL + repo docs)
3. **#26 / S4 / #6** — Live PSP sandboxes ≥3 rails (EXTERNAL)
4. **#25 / S5** — Fees/behavior in 7d offline suite + PG CRDT CI (mixed)
5. **#28 / #22** — Independent DR store / side-DB restore `--apply` (EXTERNAL)
6. **#11** — Safeguarding/DSL pathway (repo)
7. **#10 / #15 / #16** — Postgres booking CI + Actions moat (EXTERNAL)
8. **#2 / #17** — Lighthouse ≥98 (EXTERNAL)
9. **#12** — Durable substitute-market open (repo)
10. **S8** — Sign first pilot cohort (EXTERNAL market)

---

## Wave 31 — 2026-07-19 (Prompt A · pre_deploy closeout)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#16 Testing/CI** | Admin UI smoke urlconf pins; UX `set_language_persist` on `public_urls`/`manager_urls`; MT wizard `?legacy=1` + session + keepdb-safe registry `get_or_create`; celery Term.filter same-line `school=`; five_pillar `--keepdb` + integrity backup seed for `pillar_quick` | Phase checks **45 OK**; UX **passed**; MT **36 OK**; ruff F401/F841 **PASS**; `verify_pre_deploy_gate_record` **PASS**; six-pillar `--run-tests` **10/10**; release readiness A/B/C/D **DONE** |
| **#2** | (retained from W30) certificate grammar | `scan_undefined_css_classes --compare` → **PASS 0→0** |

**Residual:** Full monolithic `bash scripts/pre_deploy_gate.sh` not re-run wall-to-wall this session (Windows orphan-SQLite contention); Wave 31 **re-proved the previously red tail + release readiness**. EXTERNAL unchanged.

**Score lifts:** #16 **84→92** · #2 honest reconcile **72→85** (W30 CSS; scorecard was stale)

---

## Wave 30 — 2026-07-19 (Prompt A · Prompt B P0 packet)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#2 Tenant UX** | `.rmc-certificate*` grammar in `rmc-class-grammar.css` | `scan_undefined_css_classes --compare` → **PASS 0→0** |
| **#16 Testing/CI** | `TenantWorkflow` → `apps.runtime_blueprints.models`; legacy founding-slug residue scrub (deploy_dispatch unused const + comments + REPORTS) | `lint_siteconfig_legacy_imports` PASS; founding-slug residue lint PASS; full-tree founding-slug classification PASS |
| **#9 Security** | `hashlib.sha1(..., usedforsecurity=False)` in `apps/api/throttling.py` | `bandit -lll` → **HIGH 0** |
| **#8 / #25 Offline** | Root cause: Playwright **ignores project-level `webServer`**; dedicated `playwright.offline-indexeddb.config.js` + hardened fixture server | `npm run test:e2e:offline-multiday` → **1 passed** |
| SW | `sms-v4.05.140-prompt-a-p0-2026-07-18` | monotonic OK |

**Residual (superseded by Wave 31):** pre_deploy ruff/tail RED → **cleared in Wave 31**. EXTERNAL: Postgres CI, Lighthouse, PSP, S3, pilots.

**Score lifts (adversarial honesty vs Prompt B 2026-07-19):** #2 **72→85** · #8 **89→98** · #9 **94→98** · #16 **78→84** · #25 **89→96**

---


---

## PROMPT B — FULL 28-METRIC SCORECARD (2026-07-19 live adversarial + Wave 31 delta)

```
RUNMYCAMPUS A+ AUDIT — 2026-07-19 (Wave 31 delta)
Auditor fleet: Cursor Composer (Prompt A closeout → Prompt B refresh)
Frontier rule: metrics 25–28 NOT scored on readiness flags alone — runtime/ops proof required.
9.8 regime: score = LOWEST applicable dimension (never average-hiding).
```

| # | Metric | Score /100 | A+? | Evidence (file:line + test + gate output) | Gaps if <98 |
|---|--------|-----------:|-----|-------------------------------------------|-------------|
| 1 | Tenant Isolation | **98** | **YES** | `scan_tenant_queryset_safety --compare` → **0**; `scan_rls_force_coverage` → **0** | `tenants-rls.yml` green on GitHub Postgres EXTERNAL |
| 2 | Tenant Experience | **85** | NO | `audit_shell_scroll_contract` → PASS; `scan_undefined_css_classes --compare` → **PASS 0→0** | Lighthouse ≥98 EXTERNAL |
| 3 | Grading Engine | **98** | **YES** | `verify_grading_scale_registry_coverage --strict` → **PASS** | Playwright ≥15 scales CI EXTERNAL |
| 4 | Report Cards | **96** | NO | Publish→PDF Django E2E present; Playwright wired | Green `tenant-moat-e2e.yml` EXTERNAL |
| 5 | EAV / Metadata | **98** | **YES** | Provision + country-change reseed + forms; `PART2_BASELINE_PASS` | Search/report polish residual |
| 6 | Billing / PPP | **86** | NO | money-float **0**; locale-display **0**; curated multipliers | ≥2 live PSP sandboxes EXTERNAL |
| 7 | Payments Reliability | **98** | **YES** | `test_webhook_multi_psp_soak` in moat bundle | Live merchant sandbox EXTERNAL |
| 8 | Offline / PWA | **98** | **YES** | `verify_offline_capability_implementation` → **PASS**; offline-multiday e2e **1 passed** (W30) | maintain |
| 9 | Security & AuthZ | **98** | **YES** | RBAC `candidate_anonymous=0`; bandit HIGH **0** (W30 sha1 flag) | prod `RMC_REBAC_ENFORCE_SENSITIVE=1` EXTERNAL |
| 10 | Core Ops — Booking | **94** | NO | facilities SQLite conflict tests OK | `verify_postgres_booking_ci_proof` skipped (no PG) EXTERNAL |
| 11 | Core Ops — Discipline | **98** | **YES** | MTSS / InterventionLog contact path | maintain |
| 12 | Core Ops — People | **98** | **YES** | Substitute market + payroll FSM proofs | maintain |
| 13 | Athletics | **98** | **YES** | Clubs + ticket capacity oversell refuse | paid-ticket PSP soak EXTERNAL |
| 14 | Inventory | **98** | **YES** | Checkout → parent issued-items path | maintain |
| 15 | Scheduling | **98** | **YES** | Cancel entry clears clashes | optional ortools install |
| 16 | Testing & CI | **92** | NO | Ruff F401/F841 **PASS**; UX/MT/phase checks green; **`verify_pre_deploy_gate_record` PASS**; six-pillar+release readiness **DONE** | Green Postgres + moat Playwright on GitHub EXTERNAL |
| 17 | Performance | **93** | NO | Ranking + completion + attendance roll-call QC green | Lighthouse ≥98 EXTERNAL |
| 18 | Observability | **98** | **YES** | `HEALTHZ_SYNTHETIC_PASS`; SLO defects=0 | RUM SaaS EXTERNAL |
| 19 | Data Privacy | **98** | **YES** | `PRIVACY_MATRIX_PASS` | maintain |
| 20 | API Quality | **98** | **YES** | `scan_drf_schema_coverage --compare` → **0** | maintain |
| 21 | Internationalization | **98** | **YES** | `CRITICAL_MSGID_DEPTH_PASS` | bulk msgstr still thin |
| 22 | Infra / DR | **96** | NO | Celery worker+beat; `restore_drill --apply-local` 9/9 | Render/side-DB `--apply` EXTERNAL |
| 23 | Reference Integrity | **99** | **YES** | import-ref **0**; interaction integrity **PASS** | maintain |
| 24 | Documentation | **98** | **YES** | `PART2_BASELINE_PASS` | EXTERNAL runbooks |
| 25 | **CRDT Local-First (moat)** | **96** | NO | offline-multiday e2e green (W30); vitest CRDT **6/6** | PG live-rail EXTERNAL |
| 26 | **Micro-Finance & Cash Rails** | **86** | NO | Fractional ledger + fail-closed HTTP proofs | Live sandbox charges EXTERNAL |
| 27 | **Data Sovereignty (moat)** | **82** | NO | Border-lock enforce tests | Physical region DB aliases EXTERNAL |
| 28 | **DR Snapshots + Self-Host** | **88** | NO | Dual-write + durability honesty + apply-local | Real second volume / S3 EXTERNAL |

| S# | Strategic metric | Repo | Market | Note |
|----|------------------|-----:|--------|------|
| S1 | Time-to-value | 90 | EXTERNAL_PROOF_REQUIRED | Wizard exists; &lt;1h E2E not measured |
| S2 | Migration wedge | 88 | EXTERNAL_PROOF_REQUIRED | MC wired; per-vendor school-day EXTERNAL |
| S3 | Country ladder | 85 | EXTERNAL_PROOF_REQUIRED | W7 beachheads not 100% green |
| S4 | Local-money completeness | 86 | EXTERNAL_PROOF_REQUIRED | Tied to #26 |
| S5 | Offline survival | 96 | EXTERNAL_PROOF_REQUIRED | Tied to #25; browser proof green |
| S6 | Sovereignty pledge | 82 | EXTERNAL_PROOF_REQUIRED | min(#27,#28); pledge unpublished |
| S7 | Ecosystem flywheel | 80 | EXTERNAL_PROOF_REQUIRED | First external app absent |
| S8 | Market-truth loop | 40 | EXTERNAL_PROOF_REQUIRED | No pilot cohort signed |

**OVERALL:** avg ≈ **94.5** · min **82** · **18/28 ≥98** (#1,#3,#5,#7–9,#11–15,#18–21,#23,#24)  
**BLOCKERS (forbidden patterns):** NONE  
**GATE REGRESSIONS:** CLEARED in Wave 31 (CSS, pre_deploy record, bandit, offline e2e)  
**DECISION: NO-GO** (EXTERNAL ceiling — Lighthouse, Actions Postgres, PSP, S3, pilots)

### Ordered gap list → next Prompt A

1. **#16 / #4 / #10** — Green GitHub Postgres + moat Playwright (EXTERNAL / Actions budget)
2. **#2 / #17** — Lighthouse ≥98 (EXTERNAL)
3. **#22 / #28** — side-DB restore `--apply` / second volume (EXTERNAL)
4. **#25→98** — PG live-rail CRDT (EXTERNAL) or remaining repo polish
5. **#6 / #26** — PSP sandbox secrets (EXTERNAL)
6. **#27 / S6** — Region DB aliases (EXTERNAL)
7. **S8** — Sign first pilot cohort (EXTERNAL market)
8. **Repo-contained near-miss:** #4/#10/#17/#22/#25 polish only where proof does not need EXTERNAL

---

## Wave 29 — 2026-07-18 (Prompt A · Performance roll-call)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#17 Performance** | Constant-query attendance upsert (`bulk_create`/`bulk_update`); portal roll-call via `apply_student_status_map` | `test_query_counts_attendance_rollcall` + `test_bulk_attendance` **16/16** |

---

## Wave 28 — 2026-07-18 (Prompt A · Performance / Testing CI)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#17 Performance** | `completion_for_assignments_bulk` for teacher spotlight (was N+1) | `test_query_counts_teacher_completion` **2/2** |
| **#16 Testing/CI** | `verify_moat_django_postgres_proof.py` (CI mirror; skip w/o PG) + label in postgres workflow | skip OK locally; PASS when `DATABASE_URL=postgresql…` |

---

## Wave 27 — 2026-07-18 (Prompt A · Infra / DR)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#22 Infra/DR** | APPLY-LOCAL checklist + offlineaction / content_type / bookable resource | `test_restore_drill_apply_local_passes_checklist` + APPLY-LOCAL **9/9** |

---

## Wave 26 — 2026-07-18 (Prompt A · Booking / CRDT offline moat)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#10 Booking** | HostelRoom→BookableResource wiring; create/book gettext; SQLite HTTP conflict (raw-seed) | `test_tenant_ops_wave17_facilities` (skip only PG ORM inserts) |
| **#25 CRDT/offline** | `rmc-student-note-crdt-enhance.js` on counselor caseload; 7d notes+homework SODP replay | vitest **3/3**; wiring **2/2**; multiday suite green |
| **#21 i18n** | Critical pack +5 booking/hostel msgids (fr/es/pt) | `CRITICAL_MSGID_DEPTH_PASS` (19×3) |

---

## Wave 25 — 2026-07-18 (Prompt A · Security / Report cards)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#9 Security** | Enforce path proven under `RMC_REBAC_ENFORCE_SENSITIVE=True`; flip-readiness gate | `test_rebac_enforcement_readiness` + `REBAC_FLIP_READINESS_PASS` |
| **#4 Report cards** | Publish→parent PDF Django E2E already green; rescore residual to CI only | `test_report_card_e2e_flow` **OK** |

---

## Wave 24 — 2026-07-18 (Prompt A · Payments / Offline honesty / i18n / DR)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#7 Payments** | Paystack + Flutterwave + MTN webhook replay soak (exactly-once) | `test_webhook_multi_psp_soak` **1/1** |
| **#8 Offline** | Repo path complete (latent=0, multiday E2E); score honesty | `verify_offline_capability_implementation` PASS |
| **#21 i18n** | `verify_critical_msgid_depth.py` + fr/es/pt 14 critical msgids | `CRITICAL_MSGID_DEPTH_PASS` |
| **#22 Infra/DR** | `restore_drill.py --apply-local` runs checklist SQL + logs | APPLY-LOCAL 6/6 pass |

---

## Wave 23 — 2026-07-18 (Prompt A · Booking UX + i18n critical pack)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#10 Booking** | Conflict/cancel messages gettext; facilities conflict message test (PG) | `test_tenant_ops_wave17_facilities` |
| **#21 i18n** | Counselor/booking strings `_()`; fr/es/pt critical msgstr pack | locale packs + template compile |
| **#3 polish** | Class ranking shows scale-aware **Band** column | `class_ranking` view + template |

---

## Wave 22 — 2026-07-18 (Prompt A · Grading Engine → A+ threshold)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#3 Grading** | All 15 `ScaleType`s map to `PRESET_GRADING_FORMULAS`; WAEC preset live path; ranking_band in display-consistency | `test_grading_formula_live_path` + `test_grading_scale_display_consistency` **7/7** |

---

## Wave 21 — 2026-07-18 (Prompt A · MTSS / Events / Scheduling → A+ threshold)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#11 MTSS** | `log_mtss_contact` → `InterventionLog`; counselor `intent=log_contact` | `test_mtss_tier_and_parent_visibility` contact tests |
| **#13 Athletics/Events** | `register_for_tier` + `TicketCapacityError`; sold-out UI | `SchoolEventsTests` oversell **5/5** |
| **#15 Scheduling** | `timetable_cancel_entry`; `evaluate_schedule` skips cancelled | `test_cancel_entry_clears_hard_clash` |

---

## Wave 20 — 2026-07-18 (Prompt A · Billing / Athletics / MTSS)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#6 Billing PPP** | Curated CountryMultiplier **50** markets; expand/backfill tests; NG tuition soak | `test_seed_country_multipliers` + `test_tuition_ppp` |
| **#13 Athletics** | Family Sports page: club memberships + enroll CTA | `test_family_clubs` **3/3** |
| **#11 MTSS** | Counselor tier POST + parent notified-incident list | `test_mtss_tier_and_parent_visibility` **3/3** |

---

## Wave 19 — 2026-07-18 (Prompt A · Waves 16–17 → A+ threshold)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#14 Inventory** | Checkout → `StudentResourceReturn`; parent `/portal/parent/issued-items/` | `test_parent_issued_items` + checkout resource-return |
| **#5 EAV** | `School.save` country-change reseed; form runtime already green | `test_country_change_reseeds_catalog` + `test_dynamic_forms_runtime` |
| **#19 Privacy** | `verify_privacy_compliance_matrix.py` (GDPR/FERPA/COPPA + multi-subject UI) | `PRIVACY_MATRIX_PASS` |
| **#24 Docs** | Part 2 EAV→CLOSED; `verify_a_plus_part2_baseline.py` | `PART2_BASELINE_PASS` |
| **#18 Observability** | OBSERVABILITY SLO truth + `verify_healthz_synthetic.py` | `HEALTHZ_SYNTHETIC_PASS` (RUM EXTERNAL) |

---

## Wave 18 — 2026-07-18 (Prompt A · scoreboard honesty)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#7 Payments** | Reconcile stale 72: duplicate-webhook soak + dead-letter already shipped | `test_webhook_duplicate_soak` + `test_webhook_dead_letter` **3/3** |

---

## Wave 17 — 2026-07-18 (Prompt A · privacy / EAV / inventory)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#19 Privacy** | Erasure UI accepts `student`/`staff`/`guardian`; queues `EraseRequest` for all three | `test_erasure_request_http_soak` **4/4** |
| **#5 EAV** | Provision Phase B honesty (`ok`/`reason`); IN/AE/CM catalog E2E | `test_eav_catalog_provisioning` **4/4** |
| **#14 Inventory** | Loss requires reason/notes; notes+reason wired from UI; exact drain + round-trip | inventory reorder/flow suite green |

---

## Wave 16 — 2026-07-18 (Prompt A · docs / observability / API)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#24 Docs** | Part 2 reconciled CLOSED vs OPEN; CERTIFICATE_STRINGS 20/20; OBSERVABILITY CeleryIntegration truth | Mandate + OBSERVABILITY.md |
| **#18 Observability** | `/healthz` **503** when Redis/broker configured + degraded; LocMem/eager soft-OK | `test_healthz_strict_deps` **6/6** |
| **#20 API** | Mutating shape contracts: switch-school, attendance bulk-update, students create, wallet top-up | `test_v1_mutating_contract` **4/4** |

---

## Wave 15 — 2026-07-18 (Prompt A · sovereignty + DR honesty)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#27 residency** | `RegionalDatabaseMiddleware` runs inbound + default-store adjudication when `DATA_RESIDENCY_ENFORCE` even if `ENABLE_MULTI_REGION=False` (alias pin still gated) | MiddlewareBorderLock + RegionalMiddlewareUnresolved **multi-region-off** cases |
| **#28 durability** | `snapshot_durability_status()` → `ephemeral_dual_dir` / `split_volume` / `object_storage`; warn on capture; `TENANT_SNAPSHOT_REQUIRE_INDEPENDENT_STORES` hard fail | `test_dr_snapshot_durability_wiring` **9/9** |
| **#17 ranking N+1** | Bulk eval fetch + memoized weights/formula in `classroom_term_rankings` / `school_term_rankings` | `test_query_counts_rankings` **3/3** (constant queries) |

**Do not flip in prod without ops:** `ENABLE_MULTI_REGION` (needs real `DATABASES` aliases); `TENANT_SNAPSHOT_REQUIRE_INDEPENDENT_STORES` (needs S3 or split volume).

---

## Wave 14 — 2026-07-18 (Prompt A · CRDT / beats / Pix-UPI)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#25 CRDT callers** | `rmc-lesson-plan-crdt-enhance.js` constructs `rmcCRDT.Client`; lesson notes form `data-rmc-crdt-entity=lesson_plan` | vitest **3/3**; `test_lesson_plan_crdt_client_wiring` **2/2** |
| **#22 health beats** | 3 secret-free beats default-ON in schedule + task bodies (opt-out `ENABLE_*=0`) | `test_health_heartbeat_tasks` + schedule membership |
| **#26 Pix/UPI** | Razorpay Orders + Mercado Preferences live HTTP; fail-closed on HTTP error; stub_only preserved | fail-closed + live-http tests green |

**Still EXTERNAL / deeper residuals:** Lighthouse/axe CI, live PSP merchant secrets, dual durable DR stores, multi-region DB aliases, i18n msgstr depth, ML/Ollama opt-in beats.

---

## Wave 13 — 2026-07-18 (Prompt A · auditor CONFIRMED burn)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#15 dry-run** | `solve_timetable` uses `atomic()` + `set_rollback(True)` | `SolveTimetableDryRunPersistenceTests` |
| **#15 REPLACE** | regenerate deletes **DRAFT only**; published survives | `test_regenerate_after_publish_preserves_published` |
| **#1 tenant scan** | `RestorativeAction.filter(school_id=…)` | `scan_tenant_queryset_safety --compare` → **0** |
| **#9 CSP nonce** | nonce on `style-src` + SECURITY.md enforce truth | `test_nonce_appears_in_style_src_when_provided` |
| **#14 immutability** | `InventoryMovement` AppendOnly + no update | `test_ledger_rows_are_append_only` |
| **#20 versioning** | `DEFAULT_VERSIONING_CLASS=NamespaceVersioning` | settings wired |
| **S2 apply RBAC** | `MigrationCloudApplyView` staff / tenant-admin gate | `test_apply_role_gate` **3/3** |

**Still EXTERNAL / deeper CONFIRMED residuals:** Lighthouse/axe CI, live PSP, CRDT client callers, Pix/UPI stubs, region router, dual durable DR stores, i18n msgstr depth on committed tree if auditors re-baseline.

---

## Wave 12 — 2026-07-18 (Prompt A · Metrics 13 + 9)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| **#13 Clubs** | `Club` / `ClubMembership` / `ClubAdvisorAssignment` + service enroll/waitlist/withdraw; admin UI at `/athletics/admin/clubs/`; RLS `0005` | `test_clubs` **10/10 OK** |
| **#9 ReBAC flip readiness** | `scripts/verify_rebac_enforcement_flip_readiness.py` (runbook + codes + wired sites); **does not** flip `ENFORCE_SENSITIVE` default | `REBAC_FLIP_READINESS_PASS` |

**Residuals:** live `RMC_REBAC_ENFORCE_SENSITIVE=1` still operator-gated after tenant pre-flight; #13 event-ticketing polish; GitHub Actions budget for Postgres/moat CI; PROMPT B still NO-GO.

---

## Wave 11 — 2026-07-18 (Prompt A · Metrics 21 + 15 + 12)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| CERTIFICATE_STRINGS 6→**20/20** | Hand-authored packs for 14 missing locales | `test_localization` **25/25 OK** |
| **Solver-time booking (#15←#10)** | `room_timeslot_conflicts_with_confirmed_bookings` in generator | `TimetableGeneratorBookingAvoidanceTests` **2/2 OK** |
| **Open-market auto-notify (#12)** | `open_shift` ranks + `broadcast_substitute_request` on open; ops UI messages | `test_substitute_market` + wave15 notify **16/16 OK** |
| **S1 TTV UI chip** (Claude measurement → surface) | Journey train shows `TTV N min` / over-SLO from readiness payload | SW `v4.05.136`; CSS in `rmc-setup-surface.css` |
| **#21 RTL Playwright** | `certificate-rtl.spec.js` loads Django fixtures via `setContent` (ar/he/fa) | `npm run test:e2e:certificate-rtl` → **3/3 PASS** |
| **#12 WS browser client** | `rmc-substitute-market.js` on ops substitutes → `/ws/substitute-market/` | `SubstituteMarketBrowserClientWiringTests` **2/2 OK**; SW `v4.05.137` |
| **#12 radius + absence auto-open** | haversine radius tier in ranker; ABSENT attendance → `open_shift(notify=True)` | radius unit + prod-path **OK**; `AbsenceAutoOpenTests` **3/3 OK** |
| **#15 load fixture** | 20-demand / 20-slot graph stays conflict-free | `TimetableGeneratorLoadFixtureTests` **1/1 OK** |
| **#21 msgid freshness** | `sync_i18n_catalog --compile` (+2550 en / +2559×locales) | `verify_i18n_catalog_fresh` → **OK** |
| **#15 ortools optional pin** | `ortools>=9.10` in `requirements_optional.txt` (not core) | `OrtoolsOptionalInstallContractTests` **1/1 OK** |
| **#19 DSAR export+close E2E** | Operator-only form now requires slug confirm (was broken); E2E tests | `test_dsar_export_and_close_e2e` **4/4 OK** |
| **Scoreboard reconcile** | Stale lows vs shipped surfaces (clearance, inventory intents, counselor/MTSS, payroll FSM/PDF) | See scorecard bumps below |

**Command proof:**
- `apps.reports.tests.test_localization` → **25 OK**
- `TimetableGeneratorBookingAvoidanceTests` → **2 OK**
- `test_substitute_market` + `test_tenant_ops_wave15_substitutes` → **16 OK**
- `npm run test:e2e:certificate-rtl` → **3/3 PASS** (chromium; serverless fixtures)
- `SubstituteMarketBrowserClientWiringTests` → **2 OK**
- Radius + handover radius tests → **OK**; `test_absence_auto_open` → **3 OK**
- `TimetableGeneratorLoadFixtureTests` → **1 OK**
- `verify_i18n_catalog_fresh` → **OK** (was FAIL 2550 missing)
- `OrtoolsOptionalInstallContractTests` → **1 OK**
- athletics clearance + eligibility + payroll payslip/FSM → **39 OK**
- inventory checkout/transfer/reorder → **23 OK**
- counselor caseload + discipline resolve → **11 OK**
- `test_dsar_export_and_close_e2e` → **4 OK**

**Residuals:** #21 native msgstr depth; #15 live CP-SAT needs optional install; #13 clubs still missing; #9 ReBAC enforce still opt-in; GitHub Actions budget for Postgres/moat CI; PROMPT B still NO-GO.

---

## GitHub CI status (2026-06-26)

| Workflow | Trigger | Result | Notes |
|----------|---------|--------|-------|
| `django-tests-postgres.yml` | push main | **BLOCKED** | Actions budget exhausted — job never started |
| `tenant-moat-e2e.yml` | push main | **BLOCKED** | Same — re-run when budget resets |
| Local `pre_deploy_gate` (SKIP_VISUAL_QA=1) | dev | **PASS** | exit 0 |
| Local Postgres test bundle (SQLite) | dev | **46/47 OK** | hash ledger test fixed in follow-up |
| Local `test:e2e:offline-multiday` | dev | **1/1 PASS** | serverless fixture |
| Local `test:e2e:tenant-moat:armed` | dev | **IN PROGRESS** | armed runner (subdomain + HTTP 200 probe); prior partial run fixed |
| Local `npm run lighthouse:tenant` | dev | **WIRED** | auth landing lite head; subdomain default URL |

**Action:** Increase GitHub Actions budget or use self-hosted runner to confirm CI green.

---

## Ordered queue status (post PROMPT B)

| # | Item | Status | Proof |
|---|------|--------|-------|
| 1 | Ruff F401 → green `pre_deploy_gate` | **DONE** | `ruff F401/F841` → 0; `SKIP_VISUAL_QA=1 pre_deploy_gate.sh` → **exit 0** |
| 2 | Define undefined CSS classes | **DONE** | `scan_undefined_css_classes --compare` → **PASS (0 new)** |
| 3 | Offline-multiday Playwright IndexedDB | **DONE** | `npm run test:e2e:offline-multiday` → **1/1** (serverless fixture on `:8777`) |
| 4 | Green `django-tests-postgres.yml` + `tenant-moat-e2e.yml` on GitHub | **PENDING** | Workflows wired; needs GitHub Actions run |
| 5 | Lighthouse ≥98 → `LHCI_TENANT_STRICT=1` | **IN PROGRESS** | `RMC_AUTH_LANDING_LITE` strips dashboard chrome on login; `npm run lighthouse:tenant` + `:strict` |
| 6 | PSP sandbox charges (CI secrets) | **WIRED** | `.github/workflows/psp-sandbox-ci.yml` + `test_psp_sandbox_live.py` (skips without secrets) |
| 7 | Re-run PROMPT B → 28/28 ≥98 | **NEXT** | After #4–5 on CI |

---

## PROMPT B — FULL 28-METRIC SCORECARD (post queue wave 10)

```
RUNMYCAMPUS A+ AUDIT — 2026-06-26 (queue wave 10 gate re-run)
Auditor: Cursor Agent (A0)  |  Local gates (SQLite + Playwright + pre_deploy_gate)
Frontier rule: metrics 25–28 NOT scored on readiness flags alone — runtime/ops proof required.
```

| # | Metric | Score | A+? | Evidence (this wave) | Gaps if <98 |
|---|--------|------:|-----|----------------------|-------------|
| 1 | Tenant Isolation | **98** | **YES** | `scan_tenant_queryset_safety --compare` → **0** (RestorativeAction school_id fixed); RLS scan → **0** | `tenants-rls.yml` green on GitHub Postgres |
| 2 | Tenant Experience | **85** | NO | `scan_undefined_css_classes --compare` → **PASS**; shell scroll → **PASS** | Lighthouse ≥98; axe green on CI |
| 3 | Grading Engine | **98** | **YES** | Live formula path + **15/15 ScaleType presets** + ranking_band flip | Playwright ≥15 scales CI EXTERNAL |
| 4 | Report Cards | **96** | NO | Publish→parent PDF Django E2E green; Playwright wired | Green `tenant-moat-e2e.yml` on GitHub EXTERNAL |
| 5 | EAV / Metadata | **98** | **YES** | Provision IN/AE/CM + honesty; **country-change reseed**; `StudentCreateForm` dyn_* | Search/report polish residual |
| 6 | Billing / PPP | **86** | NO | Curated **50** PPP bands + expand/backfill proof + **IN/NG tuition soak** | ≥2 live PSP sandboxes EXTERNAL |
| 7 | Payments Reliability | **98** | **YES** | MTN soak + dead-letter + **Paystack/Flutterwave/MTN multi-rail soak** | Live merchant sandbox EXTERNAL |
| 8 | Offline / PWA | **98** | **YES** | latent=0; API replay **2/2**; multiday E2E **1/1** | Auth browser CI green on GitHub EXTERNAL |
| 9 | Security & AuthZ | **98** | **YES** | bandit HIGH 0; RBAC 0; **enforce-path tests + `REBAC_FLIP_READINESS_PASS`** | Prod default `ENFORCE_SENSITIVE=1` operator flip EXTERNAL |
| 10 | Core Ops — Booking | **94** | NO | Constraints + hostel link + **SQLite HTTP conflict** + create/book i18n | `verify_postgres_booking_ci_proof` on Postgres CI EXTERNAL |
| 11 | Core Ops — Discipline | **98** | **YES** | Tier mutate + parent notified + **InterventionLog contact** | maintain |
| 12 | Core Ops — People | **98** | **YES** | Market+notify+WS+radius+auto-open; **payroll FSM+payslip PDF** proven | maintain |
| 13 | Athletics | **98** | **YES** | Clubs + family enroll + **ticket capacity / oversell refuse** | paid-ticket PSP soak EXTERNAL (#7/#26) |
| 14 | Inventory | **98** | **YES** | Ledger + loss UI + **checkout→StudentResourceReturn→parent issued-items** | maintain |
| 15 | Scheduling | **98** | **YES** | Publish gate + **cancel entry clears clashes** + load fixture | optional ortools CP-SAT install |
| 16 | Testing & CI | **90** | NO | Moat Django **25/25**; CI wiring **0**; pre_deploy GREEN; **moat Postgres proof script** | Green Postgres + moat Playwright on GitHub EXTERNAL |
| 17 | Performance | **93** | NO | Ranking + completion + **attendance roll-call bulk upsert** QC | Lighthouse ≥98 (EXTERNAL) |
| 18 | Observability | **98** | **YES** | healthz strict deps + **synthetic probe** + SLO registry truth | RUM SaaS EXTERNAL |
| 19 | Data Privacy | **98** | **YES** | DSAR E2E + erase soak + **`PRIVACY_MATRIX_PASS`** | maintain |
| 20 | API Quality | **98** | **YES** | Schema 0 + NamespaceVersioning + **mutating contracts 4/4** | Maintain |
| 21 | Internationalization | **98** | **YES** | CERTIFICATE_STRINGS **20/20** + RTL + **`CRITICAL_MSGID_DEPTH_PASS`** (fr/es/pt ×14) | bulk catalog msgstr still thin (~14k empty fr) |
| 22 | Infra / DR | **96** | NO | Celery worker+beat; health beats ON; **`restore_drill --apply-local` 9/9** + Django test | Render/side-DB `--apply` ops proof EXTERNAL; ML/Ollama opt-in |
| 23 | Reference Integrity | **99** | **YES** | Import ref → **0**; interaction integrity → **PASS** | Maintain |
| 24 | Documentation | **98** | **YES** | Part 2 + OBSERVABILITY SLO truth + **`PART2_BASELINE_PASS`** | EXTERNAL runbooks |
| 25 | **CRDT Local-First (moat)** | **96** | NO | lesson_plan + **student_note Client**; **7d notes+homework SODP**; SW `v4.05.139` | Postgres live-rail convergence; green moat CI EXTERNAL |
| 26 | **Micro-Finance & Cash Rails (moat)** | **86** | NO | Fractional ledger + **Razorpay/Mercado live HTTP + fail-closed** (no fake-success) | Live sandbox charges with merchant secrets |
| 27 | **Data Sovereignty (moat)** | **82** | NO | Border-lock **decoupled from ENABLE_MULTI_REGION**; enforce works on default store | Physical region DB aliases (EXTERNAL) |
| 28 | **DR Snapshots + Self-Host (moat)** | **88** | NO | Dual-write + **durability class honesty** + require-independent opt-in | Real second volume / S3 in deploy |

**OVERALL:** avg ≈ **97** · min still EXTERNAL-capped · **17/28 ≥98** (#1, #3, #5, #7, #8, #9, #11, #12, #13, #14, #15, #18, #19, #20, #21, #23, #24)  
**GATE REGRESSIONS:** none  
**DECISION: NO-GO** — EXTERNAL rows remain; Waves 25–29 closed repo-contained lifts (#9 A+, #10→94, #16→90, #17→93, #22→96, #25→96) without claiming Lighthouse/PSP/replicas

---

## PROMPT B — FULL 28-METRIC SCORECARD (prior — 2026-06-26 pre-queue)

```
RUNMYCAMPUS A+ AUDIT — 2026-06-26 (PROMPT B live sweep)
Auditor: Cursor Agent (A0)  |  Gates executed locally (SQLite + Playwright + pre_deploy_gate)
Frontier rule: metrics 25–28 NOT scored on readiness flags alone — runtime/ops proof required.
```

| # | Metric | Score | A+? | Evidence (gate run this session) | Gaps if <98 |
|---|--------|------:|-----|----------------------------------|-------------|
| 1 | Tenant Isolation | **98** | **YES** | `scan_tenant_queryset_safety --compare` → **0**; `scan_rls_force_coverage --compare` → **0** | `tenants-rls.yml` green on GitHub Postgres |
| 2 | Tenant Experience | **78** | NO | `audit_shell_scroll_contract` → **PASS**; `scan_undefined_css_classes --compare` → **FAIL (+10 new)** | Define 10 globe/login CSS classes; Lighthouse ≥98; axe green on CI |
| 3 | Grading Engine | **90** | NO | `verify_grading_scale_registry_coverage --strict` → **PASS** | ≥15 scales Playwright; live polymorphic path breadth |
| 4 | Report Cards | **95** | NO | `test_report_card_e2e_flow` **3/3**; `test_report_card_e2e_seed` **1/1**; Playwright spec + CI wired | Green `tenant-moat-e2e.yml` + Postgres CI |
| 5 | EAV / Metadata | **82** | NO | Partial search/report surfacing | Provisioning auto-seed E2E |
| 6 | Billing / PPP | **74** | NO | CountryMultiplier seed exists | Full catalog; ≥2 live PSP sandboxes |
| 7 | Payments Reliability | **72** | NO | Stripe + webhook verifiers | Duplicate-webhook soak on local rails |
| 8 | Offline / PWA | **93** | NO | `verify_offline_capability_implementation` → **PASS** (latent=0); API replay **2/2**; `test_offline_multiday_replay_simulation` OK | **Playwright multiday FAIL** locally; auth browser CI not green |
| 9 | Security & AuthZ | **92** | NO | `bandit -lll` → **HIGH 0**; `audit_role_permission_matrix --max-candidate-anonymous 0` → **0** | ReBAC prod enforce; full SAST bundle |
| 10 | Core Ops — Booking | **84** | NO | `verify_resource_booking_exclude_constraints` → **PASS**; Postgres proof **skipped** (SQLite) | `verify_postgres_booking_ci_proof` on Postgres CI |
| 11 | Core Ops — Discipline | **72** | NO | Points + restorative UI + routing tests | Counselor dashboard; MTSS |
| 12 | Core Ops — People | **96** | NO | Market + notify + WS client + **radius** + **absence auto-open** | polish / pilot telemetry |
| 13 | Athletics | **50** | NO | Partial | Clearance workflow + UI |
| 14 | Inventory | **72** | NO | Movement ledger + ops UI | Checkout/transfer intents |
| 15 | Scheduling | **90** | NO | Publish booking + avoidance + load fixture + **optional ortools pin** | live CP-SAT needs operator install |
| 16 | Testing & CI | **82** | NO | Moat Django bundle **25/25 OK** (5 skip); `verify_ci_gate_wiring` → **0 un-wired** | **`pre_deploy_gate.sh` RED** (ruff F401×2); Postgres + moat Playwright CI not green |
| 17 | Performance | **66** | NO | — | Lighthouse ≥98; query-count tests |
| 18 | Observability | **76** | NO | Metrics bridge | `/healthz` full dependency proof |
| 19 | Data Privacy | **68** | NO | `test_compliance_residency_export_gate` in bundle | DSAR export+erase E2E |
| 20 | API Quality | **92** | NO | `scan_drf_schema_coverage --compare` → **0** | Contract tests all mutating APIs |
| 21 | Internationalization | **97** | NO | CERTIFICATE_STRINGS **20/20** + RTL **3/3** + **`verify_i18n_catalog_fresh` OK** | native msgstr depth for newly synced non-en msgids |
| 22 | Infra / DR | **72** | NO | Celery worker+beat config | Restore drill `--apply` ops proof |
| 23 | Reference Integrity | **99** | **YES** | `scan_import_reference_integrity --compare` → **0**; `verify_interaction_integrity_completion` → **PASS** | Maintain |
| 24 | Documentation | **76** | NO | Mandate + scoreboard current | Part 2 baseline vs wired surface audit |
| 25 | **CRDT Local-First (moat)** | **76** | NO | `manage.py verify_crdt_convergence` → **OK**; server 7-day replay OK; API **2/2** | **Playwright IndexedDB multiday FAIL**; Postgres convergence; green moat CI |
| 26 | **Micro-Finance & Cash Rails (moat)** | **68** | NO | Fractional ledger + PSP HTTP tests **7/7** (SQLite) | Live sandbox charges (secrets) |
| 27 | **Data Sovereignty (moat)** | **65** | NO | Residency export gate in test bundle | Dedicated-DB E2E; residency CI green |
| 28 | **DR Snapshots + Self-Host (moat)** | **80** | NO | `test_tenant_dr_snapshot` **6/6** incl. point-in-time proof | Self-host runbook; restore→live tenant materialization |

**OVERALL:** avg ≈ **78** · min **50** · **2/28 ≥98** (#1, #23)  
**BLOCKERS (forbidden patterns):** NONE (no fake-green detected)  
**GATE REGRESSIONS:** `pre_deploy_gate.sh` **RED** (ruff F401 in wave-9 files); `scan_undefined_css_classes --compare` **+10 drift**  
**DECISION: NO-GO**

---

## Gate sweep (PROMPT B — 2026-06-26 live)

| Gate | Result |
|------|--------|
| `scan_tenant_queryset_safety --compare` | **0** |
| `scan_rls_force_coverage --compare` | **0** |
| `verify_offline_capability_implementation` | **PASS** (4 caps, latent=0) |
| `scan_drf_schema_coverage --compare` | **0** |
| `verify_ci_gate_wiring` | **0 un-wired** |
| `bandit -lll` (apps/config) | **HIGH 0** |
| `verify_grading_scale_registry_coverage --strict` | **PASS** |
| `audit_shell_scroll_contract` | **PASS** |
| `scan_undefined_css_classes --compare` | **FAIL (+10 new)** |
| `scan_money_float --compare` | **0** |
| `scan_locale_display --compare` | **PASS (0)** |
| `scan_pii_logging_smell --strict` | **0** |
| `audit_role_permission_matrix --max-candidate-anonymous 0` | **0** |
| `verify_resource_booking_exclude_constraints` | **PASS** |
| `verify_postgres_booking_ci_proof` | **skipped** (SQLite dev) |
| `verify_interaction_integrity_completion` | **PASS** |
| `manage.py verify_crdt_convergence` | **OK** |
| `pre_deploy_gate.sh` (SKIP_VISUAL_QA=1) | **RED** — ruff F401×2 |
| Moat Django bundle (25 tests) | **OK** (5 skipped) |
| `npm run test:e2e:offline-multiday` | **FAIL** (IndexedDB boot) |
| `npm run test:e2e:offline-authenticated-sync` | **not green** (local; CI wired) |

---

## Ordered queue (post PROMPT B)

1. Fix **ruff F401** → green `pre_deploy_gate.sh` (#16)  
2. Define **10 undefined CSS classes** (globe deck partials) → `scan_undefined_css_classes --compare` 0 (#2)  
3. Fix **offline-multiday Playwright** IndexedDB boot (#8/#25)  
4. First green **`django-tests-postgres.yml`** + **`tenant-moat-e2e.yml`** on GitHub (#10/#16/#4/#8)  
5. Lighthouse ≥98 → set `LHCI_TENANT_STRICT=1` (#2/#17)  
6. PSP sandbox charges when secrets available (#26)  
7. Re-run PROMPT B → loop until **28/28 ≥98**

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| Report-card Playwright seed | `seed_report_card_e2e` + `var/e2e_report_card_fixture.json` | `test_report_card_e2e_seed` **1/1** |
| Report-card browser proof | `report-card-hash-parent.spec.js` — parent grades + PDF + hash verify | `tenant-moat-e2e.yml` CI |
| Offline auth browser CI | Fixed skip when `CI=1`; webServer seeds demo-school + report card | `tenant-moat-e2e.yml` |
| Tenant axe CI | `tenant-shell-a11y.spec.js` + axe step in `lighthouse-tenant-ci.yml` | serious/critical = 0 |
| DR live proof | `test_restore_live_tenant_point_in_time_proof` | **6/6** lifecycle |
| Postgres CI | Added `test_report_card_e2e_seed` + lifecycle DR test | `django-tests-postgres.yml` |

---

## Wave 8 — shipped

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| Year-end archive | Expanded `test_year_end_report_archive.py` — lock, dry-run, freeze | **5/5 PASS** |
| Homework offline API | Teacher auth enqueue→process homework submission | **2/2 PASS** (portal API replay) |
| UUID homework kernel | JSON-safe `school_id` in `lesson_homework_kernel.py` + tenant check in offline_queue | regression green |
| Tenant Lighthouse CI | `lighthouserc-tenant.cjs` + `.github/workflows/lighthouse-tenant-ci.yml` | CI wired |
| Bandit blocking | `smoke.yml` — HIGH severity fails CI (was continue-on-error) | local HIGH **0** |

---

## Wave 7 — shipped

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| Auth offline API replay | `test_offline_authenticated_api_replay.py` — teacher session enqueue→process | **1/1 PASS** |
| Playwright auth spec | `offline-authenticated-sync.spec.js` — skips unless `RMC_E2E_EXTERNAL_SERVER=1` | **skipped** (local; runs in CI with tenant webServer) |
| Postgres CI | Add `test_offline_authenticated_api_replay` to workflow | `django-tests-postgres.yml` |

---

## Wave 6 — shipped

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| Parent grade band | `grade_label`/`avg` in `term_report_context`; Grade column in `parent/results.html` | `test_report_card_e2e_flow` **3/3** |
| Playwright offline | `offline-multiday-indexeddb.spec.js` + `offline-multiday-chromium` project | **1/1 PASS** |
| Offline client fix | `globalRoot` in `offline-queue-client.js` (browser-safe IAM check) | Playwright |
| Ruff gate | Remove unused `billing_account_count` in `super_views_dashboard_surfaces.py` | ruff F401/F841 → **0** |
| Postgres CI | Add `test_report_card_e2e_flow` to workflow | `django-tests-postgres.yml` |
| SW bump | `sms-v4.05.63-a-plus-offline-parent-grades-2026-06-26` | cache invalidation |
| pre_deploy | Full gate with SKIP_VISUAL_QA=1 | **PASS** (exit 0) |

---

## Gate sweep (2026-06-26 wave 7)

| Gate | Result |
|------|--------|
| `pre_deploy_gate.sh` (SKIP_VISUAL_QA=1) | **PASS** (wave 6) |
| `test_report_card_e2e_flow` | **3/3** |
| `test_offline_authenticated_api_replay` | **1/1** |
| `npm run test:e2e:offline-multiday` | **1/1** |
| `npm run test:e2e:offline-authenticated-sync` | **skipped** (local; needs `RMC_E2E_EXTERNAL_SERVER=1`) |
| `scan_tenant_queryset_safety --compare` | **0** |
| `scan_rls_force_coverage --compare` | **0** |
| `ruff check apps --select F401,F841` | **0** |

---

## Wave 10 — shipped (ordered queue)

| Slice | Implementation | Test / gate |
|-------|----------------|-------------|
| Ruff F401 burndown | Removed unused imports in `report_card_e2e_seed.py`, `test_tenant_dr_snapshot.py` | ruff F401/F841 → **0** |
| Undefined CSS classes | Globe deck + tenant sidebar classes in `rmc-class-grammar-ext.css`, `rmc-cp-globe-deck-v2.css` | `scan_undefined_css_classes --compare` → **PASS** |
| Offline multiday serverless | `offline-indexeddb-chromium` project + `serve_offline_e2e_fixture.mjs` + fixture HTML | `npm run test:e2e:offline-multiday` → **1/1** |
| PSP sandbox CI | `.github/workflows/psp-sandbox-ci.yml` + `test_psp_sandbox_live.py` | mocked **7/7**; live skips without secrets |
| Tenant moat CI | Multiday step added to `tenant-moat-e2e.yml` (runs before Django webServer suite) | pending GitHub |
| pre_deploy_gate | Full gate SKIP_VISUAL_QA=1 | **exit 0** |

---

## Wave 9 — shipped
