# Migration Cloud — Real-World Scenarios

End-to-end walk-throughs of how the Universal Migration Cloud handles five
schools with genuinely different sources, sizes, and constraints. Each
scenario calls out which pipeline layer does the work and where the AI
bridge contributes vs. where deterministic logic is sufficient.

For the architectural overview see [MIGRATION_UNIVERSAL_INTAKE.md].
For the seeded ontology see [`apps/migration_cloud/ontology/catalog.py`].

The promise restated: **any platform, any size, holistic, hours not weeks.**

---

## Scenario 1 — St. Mary's K-8 (Catholic school, 250 students, FACTS/RenWeb)

**Profile:** Small parish school, single campus, registrar with one foot
out the door (her last day is in three weeks). Wants to move off FACTS
because the sacrament-tracking module is too rigid. Data drop is an export
from FACTS plus 4 Excel sheets the registrar maintained on the side
(sacrament dates, parent-volunteer hours, lunch-account top-ups, alumni).

**Intake:** Operator drops a 38 MB ZIP onto `/super/migration/`.
- `BundleIngestionService.ingest(BundleSpec(intake_method=ARCHIVE, ...))`
- ArchiveIntakeAdapter expands to 12 CSV files + 4 XLSX sheets under one
  parent archive artifact.
- Bundle status: `INGESTING`.

**Profile (Phase U2):**
- Each artifact gets a deterministic `ArtifactProfile` (columns, types,
  samples, regex shapes, PII flags, locale hints).
- The profiler infers `date_format = "%m/%d/%Y"` (US shape) because no
  values have a day component > 12 in the day position.
- Bundle status: `PROFILED`.

**Classify (Phase U3):**
- `source` classifier sees `StudentID`, `FirstName`, `LastName`,
  `FamilyID`, `PrimaryParentEmail`, `SacramentDate` → matches FACTS
  signature at confidence 0.87 (no AI tiebreaker needed).
- `domain` classifier per artifact:
  - `students.csv` → `students` (0.91, overlap)
  - `families.csv` → `guardians` (0.78)
  - `sacrament_dates.xlsx` → top-1 `custom_fields` at 0.0 (no overlap);
    AI tiebreaker picks `custom_fields` with reasoning "sacrament data
    has no canonical domain in the seeded ontology — preserve as
    DynamicField on the student record."
- Bundle status: `CLASSIFIED`.

**Map (Phase U4):**
- Most students.csv columns map via Layer 1 (exact alias):
  `FirstName→first_name`, `LastName→last_name`, etc.
- `Grade` → `grade_level` via Layer 2 token similarity (0.83).
- `Religion` and `Sacraments_Received` → custom_fields (no canonical
  match; never dropped).

**AI usage:** 1 LLM call total for the whole bundle (the sacrament XLSX
domain tiebreaker). Estimated wall-clock: 4 minutes.

---

## Scenario 2 — Cardinal Heights Academy (private HS, 1,200 students, Blackbaud)

**Profile:** Independent K-12 day school, Blackbaud since 2007. 6 years
of transcripts, donor pipeline, athletic rosters, financial-aid awards.
Want to leave because of cost. Heaviest concern: transcript fidelity
across 6 years of grading-scale changes (school moved from numeric to
letter grades in 2022).

**Intake:** Blackbaud SKY API token + a separate 110 MB ZIP of historical
transcripts in PDF.
- Token → `IntakeMethod.OAUTH_FOLDER` (Phase U7 stub today; for now
  operator exports CSVs from Blackbaud manually and uploads).
- PDFs → `IntakeMethod.ARCHIVE`. Each PDF becomes one artifact with
  `detected_format = PDF` (OCR scheduled Phase U7).

**Profile + Classify:**
- CSVs get profiled; source classifier matches Blackbaud at 0.93
  (`UserHostID`, `AdvisorHostID`, `OnRecord` headers).
- Transcripts artifact gets `detected_format = PDF`, `domain = transcripts`
  (overlap on filename only since profiler can't read PDF text in U2).

**Map (Phase U4):**
- `UserHostID` → `external_id` (alias)
- `GradeLevel` → `grade_level` (alias)
- `EnrollmentStatus` → `enrollment_status` (alias) with
  `enum_rewrite` transformer attached
  (`mapping={"Currently Enrolled": "active", "Withdrawn": "withdrawn", ...}`)
- Multi-year transcripts: mapper attaches `grading_scale_to_canonical`
  transformer with `scale_map` derived from the school's old/new scale
  documentation. Each transcript line normalizes to percent so canonical
  storage is uniform; the renderer reproduces the school's preferred
  scale at view time.

**AI usage:** 3 LLM calls (enum mapping verification, donor-field
classification, scale-conversion sanity check). Estimated wall-clock:
~25 minutes (would be < 5 minutes once OAuth + OCR land in Phase U7).

---

## Scenario 3 — Lincoln Unified School District (public, 8,400 students, PowerSchool, OneRoster export)

**Profile:** Mid-size public district. Cutover over winter break — every
day of downtime matters. They already publish a OneRoster v1.2 export
to Clever/ClassLink, so the accelerator path applies.

**Intake:** OneRoster CSV bundle as ZIP (manifest.csv + users.csv +
students.csv + teachers.csv + parents.csv + courses.csv + classes.csv +
enrollments.csv + academicSessions.csv + demographics.csv).
- `ArchiveIntakeAdapter` expands. 10 child artifacts under one parent.

**Profile + Classify:**
- Profile is fast (CSVs are tight). Source classifier matches the
  `oneroster` signature at 0.95 from `sourcedId`, `enabledUser`, role
  columns. No AI call needed.
- Domain classifier still runs per artifact for audit, but the
  accelerator overrides.

**Accelerator (Phase U9):**
- `OneRosterV1p2InboundAccelerator.is_handle_supported(bundle)` returns
  True (manifest.csv present).
- `execute()` pre-classifies each of the 10 known files to its canonical
  domain + canonical column mappings:
  - `users.csv → staff` (filtered to teacher/admin role)
  - `students.csv → students`
  - `enrollments.csv → enrollment`
  - ... etc.
- Vendor enum tables attached:
  `{"enabledUser": {"true": "active", "false": "inactive"}, ...}`

**Map (Phase U4):**
- `_apply_accelerator_then_map` honors the accelerator's mappings for
  known columns and runs the universal mapper for any extra columns
  Lincoln added (e.g. `state_attendance_code`, `iep_flag`).
- 100% of OneRoster-spec columns mapped at confidence 0.99. The 4 extra
  columns: 2 land via alias (state_attendance_code → custom_fields,
  iep_flag → custom_fields), 2 via AI tiebreaker (`graduation_pathway`,
  `efl_status` both → `custom_fields.*` with operator review queued).

**AI usage:** 2 LLM calls total (the two unknown columns). Estimated
wall-clock: 6 minutes for 8,400 students.

---

## Scenario 4 — Aalborg International School (450 students, 12 Google Sheets, no formal SIS)

**Profile:** Small international school in Denmark. Never had a real SIS —
the registrar runs everything in a shared Google Drive folder with 12
spreadsheets that have evolved over 4 years. Most headers are Danish
("Fornavn", "Efternavn", "Klasse", "Forælder Telefon"). Sheets vary in
shape (one has merged header cells; another stores grades column-per-term).

**Intake:** Operator points the wizard at the Google Drive folder
(`IntakeMethod.OAUTH_FOLDER` — stub until Phase U7; today the registrar
exports the 12 sheets as XLSX and uploads a ZIP).
- `ArchiveIntakeAdapter` expands. 12 child artifacts.

**Profile:**
- For sheets with merged header cells, the profiler grabs the first data
  row's headers (since the merged cell row has only one populated column).
- Locale hints: `date_format = "%d-%m-%Y"` (EU shape), `decimal_separator
  = ","`, `default_country_code = "+45"` from the operator's signup
  metadata.

**Classify:**
- Source classifier: no signature matches → AI tiebreaker says
  `unknown_custom` (confidence 0.62). Falls through gracefully.
- Domain classifier per artifact:
  - "Elever 2025-26.xlsx" headers `Fornavn`, `Efternavn`, `Klasse`,
    `Fødselsdato` → matches `students` ontology synonyms in Danish? No
    — Danish isn't seeded yet. Overlap score 0.0 → AI tiebreaker picks
    `students` at 0.88 with reasoning "Fornavn=first name, Efternavn=
    last name, Klasse=class, Fødselsdato=date of birth (Danish)."

**Map:**
- For each Danish column, Layer 1 (alias) and Layer 2 (token similarity)
  miss because the ontology doesn't carry Danish synonyms. Layer 3
  (value-shape) provides partial signal (Fødselsdato values match date
  regex). Layer 4 (AI tiebreaker) picks the canonical fields one by one.
- Auto-transformers attached:
  - `Fødselsdato` → `date_iso_normalize` with `date_format = "%d-%m-%Y"`.
  - `Forælder Telefon` → `phone_e164` with `default_country_code = "+45"`.

**Operator follow-up:** Operator reviews the AI mappings in the wizard
(Phase U6) and clicks "Save as profile" — the next time Aalborg runs a
delta migration, the saved profile re-uses these mappings and skips the
AI calls entirely.

**Bonus:** Operator extends the ontology with Danish synonyms via the
`RuntimeDefaults` overlay key
`migration_cloud.ontology.synonyms_overlay`. Every Danish school after
Aalborg gets alias-layer matches for free.

**AI usage:** 14 LLM calls (one per column needing tiebreaker).
Estimated wall-clock: 8 minutes.

---

## Scenario 5 — Riverside Adult Learning (university extension, 1,500 students, custom MS Access database)

**Profile:** Continuing-ed program running a 12-year-old MS Access
database (`certificates.accdb`). Custom schema: 14 tables, half of which
are normalized junction tables. No external standard fits.

**Intake:** Operator exports each table to CSV (Access → File → Export →
CSV per table) and uploads a ZIP of 14 CSVs.
- Phase U7 (later) will accept the `.accdb` directly via `DATABASE`
  adapter and walk tables internally.

**Profile:**
- Each table's profile is straightforward. Foreign-key relationships in
  the source are *inferred at apply time* in Phase U5 from value-overlap
  analysis (Phase U5 introduces `relationship_inferrer.py`); for now they
  land as raw FK strings.

**Classify:**
- Source classifier: no match → `unknown_custom`. AI tiebreaker
  confirms.
- Domain classifier per artifact:
  - `Students.csv` → `students` (overlap 0.74)
  - `Certificates.csv` → `custom_fields` (no canonical domain; this is
    Riverside's bespoke certificate-tracking schema)
  - `Enrollments_2023.csv`, `Enrollments_2024.csv`, ... → all map to
    `enrollment` (overlap on student_id, course_id, start_date)

**Map:**
- `Students.csv`: standard alias + token-similarity mappings.
- `Certificates.csv`: every column → `custom_fields.<normalized>` since
  domain is `custom_fields`. Riverside's DynamicFieldDefinition table
  ends up with 11 new field defs after apply.

**Apply (Phase U5):**
- Apply runs 14 child `MigrationRun`s in parallel (one per table) with
  FK ordering inferred from the canonical ontology
  (`students` before `enrollment` before `grades`, etc.).

**AI usage:** 6 LLM calls (source confirmation + 5 domain tiebreakers).
Estimated wall-clock: 12 minutes.

---

## What the AI does — and what it does not

**Does:**
- Picks between deterministic candidates when none meet threshold (source,
  domain, field-mapping tiebreaker).
- Suggests auto-transformers for values whose shape is ambiguous.
- Reads multilingual column names against the canonical ontology.
- Generates one-sentence human-readable reasoning for every choice (audit
  log → operator review).

**Does NOT:**
- Replace deterministic alias matching. ≥95% of columns in a typical
  bundle map without an LLM call.
- Write to tenant tables. The orchestrator owns persistence + RLS
  scoping + idempotency + quarantine + rollback.
- Hallucinate fields. Every proposal is constrained to a fixed allow-list
  (known sources, known domains, ontology fields, registered transformers).
- Block the pipeline. When AI is disabled (`RUNMYCAMPUS_AI_ENABLED=0`)
  or unreachable, the bridge returns `None` and the deterministic layers
  decide. Bundles still complete — they just lose the tiebreaker boost
  and quarantine more aggressively.

**Where AI confidence threshold defaults live**
(`apps.migration_cloud.defaults._SEED`):
- `migration_cloud.classifier.source_min_confidence = 0.65`
- `migration_cloud.classifier.domain_min_confidence = 0.70`
- `migration_cloud.mapper.field_min_confidence = 0.80`

Lower thresholds = more AI usage + more auto-mappings + more risk of
mismaps. Raise them via `RuntimeDefaults` per tenant once trust in the
AI layer is established.

---

## Operator call-site

```python
from apps.migration_cloud.models import IntakeMethod
from apps.migration_cloud.pipeline import advance_bundle
from apps.migration_cloud.services import BundleIngestionService, BundleSpec

# 1. Intake
ingestion = BundleIngestionService().ingest(BundleSpec(
    intake_method=IntakeMethod.ARCHIVE,
    handle="/srv/migration/incoming/aalborg_sep_2026.zip",
    school_id=42,
    schema_name="tenant_42",
    label="Aalborg cutover Sept 2026",
    source_hint="",                     # let the classifier decide
    sla_tier="small",
    idempotency_key="aalborg-2026-09-cutover",
    triggered_by_id=operator.id,
))

# 2. Advance through profile → classify → (accelerator?) → map
summary = advance_bundle(bundle_id=ingestion.bundle_id, use_accelerator=True)

# summary['status']        → 'MAPPED'
# summary['source']        → e.g. 'unknown_custom' or 'oneroster'
# summary['per_artifact']  → {path: {domain: 'students', ...}}
# summary['ai_calls']      → e.g. 14
```

Phase U5 introduces `apply_bundle(bundle_id)` which fan-outs one
`MigrationRun` per (domain, artifact), runs the transformers, persists
to the tenant under RLS, and produces a reconciliation report. Phase U6
wraps this whole flow in a drag-and-drop wizard at `/portal/configure/
migration/`.
