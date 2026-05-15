# Comprehensive Test Plan — Buea Dual-Curriculum (GCE + Technical)

**Goal:** Real user testing and real-world scenarios so the site runs successfully.  
**Focus:** English education system in Cameroon; technical school with specialties/workshops; Form 5 & 7 take GCE.  
**Password for all created users:** `Test1234` (simple seed) or align Buea seed to `Test1234` — see below.  
**Output:** Log every bug, redundancy, gap, and improvement in **`test_finding.md`** at project root.

---

## Where Testing Lives in the Codebase

| What | Where |
|------|--------|
| **Synthetic Buea data** | `apps/academics/management/commands/seed_buea_synthetic.py` (200/500 students, General + Technical, Buea localities; all passwords `Test1234`) |
| **Simple seed users** | `ensure_superuser`, `create_teacher_parent_accounts`, `seed_render_users` → admin, teacher1, Parent1, principal1 (password from env or `Test1234` locally) |
| **Evals (marks, sequences, weights)** | `apps/evals/` — models, views, AssessmentWeights (seq1/seq2/exam/mock/practical), ranking, approval, import |
| **Report cards (CRITICAL)** | `apps/reports/` — term/annual PDF, publish status, parent download views; templates in `templates/reports/` |
| **Publish term results** | `apps/reports/` — `TermPublishStatus`, `reports:publish_term_results` |
| **Rollover** | `apps/accounts/views.py` → `rollover_year`; URL `accounts:rollover_year`; moves students, can lock source year |
| **Finance / arrears** | `apps/finance/` — Invoice, Payment, FeePlan, FeeItem |
| **GCE / certification** | `apps/academics` — CertificationExamSession, CertificationCandidate; EMIS export in `emis/` |
| **Test findings log** | **`test_finding.md`** (project root) — document every bug, redundancy, issue, gap, improvement |

---

## Password Standard: Test1234

- **Simple seed (admin, teacher1, Parent1, principal1):** Use `Test1234` when running locally (e.g. `create_teacher_parent_accounts --password Test1234`).
- **Buea synthetic seed:** Uses `Test1234` (DEMO_PASSWORD in `seed_buea_synthetic.py`).
- **Simple seed:** admin, teacher1, Parent1, principal1 — use `Test1234` when running create_teacher_parent_accounts locally.

---

## Phase 1: Data Seeding (“Digital Twin”)

### 1.1 Run Buea synthetic seed

```bash
python manage.py migrate --noinput
python manage.py ensure_superuser --no-input --password Test1234
python manage.py seed_buea_synthetic --scale small
```

**Verify:**

- Academic years: 2024/2025 (inactive), 2025/2026 (active).
- Terms: 3 terms for each year.
- Departments: General Education, Technical Education.
- Specialties: General + Technical (e.g. Building, Electricity, Home Economics, Accounting if present).
- Classrooms: General (Form 1–Upper Sixth) and Technical (Year 1–7).
- Students: ~200 (small) with Buea localities (Molyko, Great Soppo, Mile 17, Bonduma), matricules BUEA/2025/001…
- Teachers: teacher_buea_01 …; Parents: parent_buea_001 …; Admins: admin_buea_01 …; Bursar: bursar_buea.
- Evaluations: marks for first term; AssessmentWeights (seq1, seq2, exam, mock, practical).
- Finance: FeePlan, Invoice (some with debt).
- GCE: CertificationExamSession, CertificationCandidate for Form 5 / Upper Sixth.
- Reports: TermPublishStatus for the active term where applicable.

**Log in test_finding.md:** Missing data, wrong localities, wrong coefficients, or seed errors.

### 1.2 Password

- Buea seed already uses `Test1234` (DEMO_PASSWORD). No extra step needed.

---

## Phase 2: Evals — Full Coverage (MUST TEST)

### 2.1 Mark entry (teacher)

- **Action:** Log in as teacher (e.g. teacher_buea_01 / Test1234). Open evals mark entry for a class and term.
- **Test:**
  - Enter CA for seq1, seq2; exam; mock; practical where applicable.
  - **Reject invalid:** e.g. 25/20 when scale is 20 → must be rejected (validators in `apps/evals/validators.py`).
  - **Coefficients:** Verify weighted average uses subject coefficients (e.g. Maths coeff 5 vs French coeff 2) — see `apps/evals/` (ranking, services).
- **Log:** Any field missing, wrong calculation, or edit allowed when term is published/locked.

### 2.2 Sequences and weights

- **Action:** Configure AssessmentWeights for a classroom/term (seq1_weight, seq2_weight, exam_weight, mock_weight, practical_weight, score_scale).
- **Test:** Change weights; save; re-open. Enter marks and confirm final score matches expected formula.
- **Log:** Incorrect formula, weights not applied, or UI not reflecting weights.

### 2.3 Technical / workshop / industrial attachment

- **Action:** If Technical stream has “practical” or “industrial attachment” component, enter marks and ensure they feed into sequence/final grade.
- **Test:** Verify one Technical student’s report shows workshop/practical marks and they affect average.
- **Log:** Missing workshop column, wrong weight, or not syncing to report.

### 2.4 Approval and publish

- **Action:** Submit marks for approval (if workflow exists); then publish term results (reports flow).
- **Test:** After publish, teacher cannot edit marks; parent can only download if allowed.
- **Log:** Edit still allowed after publish, or publish button missing/incorrect.

### 2.5 Year lock (rollover)

- **Action:** After rollover with “lock source year”, try to edit previous year’s marks as teacher.
- **Test:** Evals views must return 403 or “year locked” (see `apps/evals/views.py` year hard lock).
- **Log:** If edits still possible after lock.

### 2.6 OCR / bulk import (if implemented)

- **Action:** Use evals import (e.g. `import_grades` or upload template) for a set of students.
- **Test:** Data appears correctly in evaluations and report context.
- **Log:** Parsing errors, wrong student/subject mapping.

---

## Phase 3: Report Cards (MOST IMPORTANT — MUST TEST)

### 3.1 Term report PDF

- **Action:** As parent of a student with published term results, open portal and download term report (PDF).
- **Test:**
  - PDF generates without 500.
  - Contains: student name, class, term, subjects, seq1/seq2/exam/mock/practical, coefficients, total, average, class position.
  - Logo and school name correct; no overlapping text or missing grades.
- **Log:** Missing subject, wrong average, wrong position, layout bug, or crash.

### 3.2 Annual report PDF

- **Action:** Download annual report for a student with full year data.
- **Test:** Same as above for full year; promotion/decision if shown.
- **Log:** Same as 3.1.

### 3.3 Financial clearance / report card block (CRITICAL GAP)

- **Current:** `apps/reports/views.py` — `parent_download_term_report` and `parent_download_annual_report` do **not** check outstanding balance/debt before allowing download.
- **Required (Buea):** Block PDF download when student has outstanding balance; show message “Please clear fees at the Bursary” and optionally trigger SMS to parent.
- **Test:** (After implementing) Create a student with unpaid invoice; as parent attempt download → must be blocked. After payment → download allowed.
- **Log in test_finding.md:** “GAP: Report card download not blocked by financial arrears” and any implementation notes.

### 3.4 Report card share link (if implemented)

- **Action:** Use shareable link (e.g. JWT or token) to access report.
- **Test:** Same debt block must apply; link must expire or be invalid after revocation.
- **Log:** If debt not checked on link access.

### 3.5 Bulk report generation

- **Action:** Trigger bulk report generation for many students (e.g. 100+).
- **Test:** No memory crash; celery/async if used; successes logged.
- **Log:** Timeouts, 500s, or wrong PDFs.

### 3.6 QR / authenticity (if implemented)

- **Action:** If report cards have QR for verification, scan and confirm it points to correct record.
- **Log:** Missing QR or wrong URL.

---

## Phase 4: Finance and Arrears

### 4.1 Invoices and fee plans

- **Action:** Check FeePlan, FeeItem for General vs Technical (e.g. Workshop Fees, PTA).
- **Test:** Technical students have workshop/fees distinct from General; invoices generated for new year.
- **Log:** Missing workshop fee, wrong amount, or invoice not generated.

### 4.2 Arrears carry-forward (rollover)

- **Current:** `rollover_year` moves students and can lock year; it does **not** create “Opening Balance” or carry debt in `apps/finance` to next year.
- **Required (Buea):** Unpaid 2024/2025 fees should appear as Opening Balance / arrears for 2025/2026.
- **Test:** (After implementing) One student with unpaid invoice; run rollover; check 2025/2026 ledger for that student.
- **Log in test_finding.md:** “GAP: Arrears not carried forward to next academic year” and any design notes.

### 4.3 Payment and report unlock

- **Action:** If payment callback (e.g. MoMo) is implemented, simulate success callback; confirm invoice status and that report download is then allowed (once 3.3 is implemented).
- **Log:** Callback not updating ledger, or report still blocked after payment.

---

## Phase 5: GCE / Certification and EMIS

### 5.1 GCE registration (Form 5 / Upper Sixth)

- **Action:** Open certification/GCE registration for a Form 5 student; upload birth certificate / photo if fields exist.
- **Test:** Only Form 5 (and Upper Sixth for AL) eligible; mandatory subjects (e.g. English, French, Maths) selectable; status “Ready for GCE Board” or equivalent when complete.
- **Log:** Wrong form allowed, wrong subjects, or missing validation.

### 5.2 GCE export format (MINESEC / Board)

- **Action:** Export candidate list (if feature exists) for GCE.
- **Test:** Date format DD/MM/YYYY; CIN 9 digits; column headers match Board template; no American date format.
- **Log:** Wrong date format, missing column, or wrong CIN.

### 5.3 EMIS export

- **Action:** Use EMIS dashboard to export students/teachers/enrollment/performance for an academic year/term.
- **Test:** Files download; content matches DB (sample check).
- **Log:** Wrong data or format.

---

## Phase 6: Rollover and Year-on-Year

### 6.1 Rollover execution

- **Action:** Run rollover: source 2024/2025 → target 2025/2026; assign next classroom per student; optionally lock source.
- **Test:**
  - Students move to target year and correct classroom (or Alumni).
  - Source year becomes read-only for evals when locked.
  - No duplicate students; matricule unchanged.
- **Log:** Wrong classroom, duplicate, or evals still editable after lock.

### 6.2 Promotion logic

- **Action:** Use rollover UI (or analytics) to see promotion suggestion (e.g. pass ≥ 10/20 General; Technical rules if any).
- **Test:** Students below threshold suggested repeat; above suggested next class.
- **Log:** Wrong threshold or wrong suggestion.

### 6.3 Archive integrity

- **Action:** After rollover and lock, login as teacher and try to edit previous year marks.
- **Test:** Must be forbidden (403 or message).
- **Log:** If edit allowed.

---

## Phase 7: RBAC and Security

- **Action:** As parent, try to access teacher mark entry or admin user list; as teacher, try to delete a student or publish reports without permission.
- **Test:** All forbidden; appropriate message or redirect.
- **Log:** Any permission bypass.

---

## Phase 8: Real-World Edge Cases

| Scenario | Action | Expected | Log in test_finding.md |
|----------|--------|----------|------------------------|
| Invalid mark 25/20 | Enter 25 in a 20-point field | Rejected | If accepted |
| Form 4 GCE registration | Try to register Form 4 for GCE | Blocked | If allowed |
| Offline / sync | (If implemented) Enter marks offline, then restore network | Data syncs, no duplicate | If not implemented or broken |
| Specialty transfer | Move student from one specialty to another mid-term | Material/fee balance updated if applicable | If missing |
| Duplicate payment callback | Send same MoMo TransID twice | Idempotent; no double credit | If double credit |

---

## Execution Order (Recommended)

1. **Phase 1** — Seed Buea; confirm data and password (Test1234 if aligned).
2. **Phase 3** — Report cards (term + annual PDF, then implement and test debt block).
3. **Phase 2** — Evals (mark entry, weights, sequences, approval, lock).
4. **Phase 4** — Finance (invoices, arrears carry-forward if implemented).
5. **Phase 6** — Rollover and promotion.
6. **Phase 5** — GCE and EMIS export.
7. **Phase 7 & 8** — RBAC and edge cases.

---

## test_finding.md — What to Document

For every test:

- **Bug:** Incorrect behavior or crash (steps, expected, actual).
- **Redundancy:** Duplicate UI, duplicate logic, or dead code.
- **Gap:** Missing feature required for Buea (e.g. report block by debt, arrears carry-forward, GCE date format).
- **Improvement:** UX, performance, or clarity (e.g. clearer message when report blocked).

Keep **test_finding.md** at project root and update it as you run through this plan.
