# UX rules audit (Section 26.5)

**Purpose:** Document which lists have search/filter/export and which forms have autosave/draft so we can close gaps and align with “no empty pages, list/form/workflow standards” (Section 26.5).

**Reference:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md Section 26; REMAINING_PLAN_AUDIT_GAPS 26.5; INCOMPLETE_ITEMS_AND_NORTH_STAR_ALIGNMENT.

---

## List standards (search / filter / export)

| Area | List | Search | Filter | Export | Notes |
|------|------|--------|--------|--------|--------|
| Students | Student list (tenant) | Yes (name, ID) | Yes (grade, status) | CSV/export available | student list views |
| Invoices | Invoice list (finance) | Yes | Yes (status, date range) | CSV | finance list views |
| Admissions | Applications | Yes | Yes (status, term) | Optional export | admissions app |
| Evals / Gradebook | Gradebook, evals | Yes | Yes (term, section) | Export / report | evals app |
| Staff | Staff list (teachers) | Yes | Yes (department) | CSV | people/backend_teacher_list |
| Parents | Guardian list | Yes | Yes (year, classroom) | CSV | people/backend_guardian_list |

**Reference implementation:** Add or verify search/filter/export on one key list (e.g. students or invoices) as the pattern; other lists follow the same UX.

**Done when:** Each major tenant-facing list has at least search + one filter; export (CSV or equivalent) where data is sensitive or bulk. **Status:** Done for Students, Invoices, Teachers, Guardians, Evals (teacher marks). Applications: when admissions module has a tenant-facing list, follow same pattern.

---

## Form standards (autosave / draft)

| Form | Autosave / draft | Notes |
|------|------------------|--------|
| Backend student create | Yes (FormDraft) | Save draft, Resume draft, Discard; siteconfig:form_draft_api |
| Student onboarding | Partial (session / step state) | Multi-step; draft can be step-level |
| Application (admissions) | Yes (FormDraft) | Backend Add applicant: Save draft, Resume draft, Discard (application_form). “Save draft” preferred |
| Grade submission | No autosave | Short form; submit on save |
| Link child (portal) | No | Short; submit once |
| Site/config (admin) | No | Admin; explicit save |

**Done when:** Long tenant-facing forms (e.g. application, onboarding) have “Save draft” or equivalent; short forms remain submit-on-save.

---

## Remaining lists/forms to prioritise

Use this checklist for sprint planning; assign one row per sprint and tick when done. See [SCOPED_WORK_NOT_DONE.md](SCOPED_WORK_NOT_DONE.md) item 2.

| List or form | Search | Filter | Export | Draft | Owner / sprint | Done |
|--------------|--------|--------|--------|-------|----------------|------|
| Applicants list (if separate from Applications) | Yes | Yes (stage) | CSV | — | Sprint 1 | [x] |
| Classes/sections list | Yes | Yes (year, dept) | CSV | — | Done | [x] |
| Documents list (backend) | Yes | Yes (type) | CSV | — | Sprint 1 | [x] |
| Application (admissions) long form | — | — | — | Save draft | Sprint 1 | [x] |
| Student onboarding (multi-step) | — | — | — | Save draft / Resume draft | Done | [x] |

**Note:** Students, Invoices, Teachers, Guardians, Evals, Applications (list) already have reference implementation. Classes/sections list and Student onboarding step-level draft are **done** (see [SCOPED_WORK_VERIFICATION.md](SCOPED_WORK_VERIFICATION.md) §1). Nothing is left partially done.

---

## Checklist 26.5

- [x] UX rules audit doc created (this file).
- [x] Reference: Student list and Invoice list have search, filter, export (CSV/PDF where applicable).
- [x] Reference: One long form (backend student create) has Save draft / Resume draft / Discard via FormDraft API.
- [x] Product/UX: Reference implementations done (Students, Invoices; backend student create draft). Prioritise using the "Remaining lists/forms to prioritise" table above; keep [SCOPED_WORK_NOT_DONE.md](SCOPED_WORK_NOT_DONE.md) in sync when items are done.
