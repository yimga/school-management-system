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
| Application (admissions) | Scoped (save progress) | Long form; “Save draft” preferred |
| Grade submission | No autosave | Short form; submit on save |
| Link child (portal) | No | Short; submit once |
| Site/config (admin) | No | Admin; explicit save |

**Done when:** Long tenant-facing forms (e.g. application, onboarding) have “Save draft” or equivalent; short forms remain submit-on-save.

---

## Checklist 26.5

- [x] UX rules audit doc created (this file).
- [x] Reference: Student list and Invoice list have search, filter, export (CSV/PDF where applicable).
- [x] Reference: One long form (backend student create) has Save draft / Resume draft / Discard via FormDraft API.
- [x] Product/UX: Reference implementations done (Students, Invoices; backend student create draft). Prioritise search/filter/export on remaining lists and draft on other long forms (e.g. application) per product.
