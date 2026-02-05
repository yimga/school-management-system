# Test Findings — Buea Dual-Curriculum & Report Cards

Document every **bug**, **redundancy**, **gap**, and **improvement** found while running the comprehensive test plan. See **docs/COMPREHENSIVE_TEST_PLAN_BUEA.md** for the full plan.

**Convention:** Use headings by phase or area; each finding: short title, severity (Critical/High/Medium/Low), steps to reproduce (if bug), expected vs actual, and recommendation.

---

## What’s missing in the code (vs comprehensive plan)

Summary of **plan vs code**: what the plan expects that is **not implemented** or only **partially implemented**.

| # | Plan requirement | In code? | Where / note |
|---|------------------|---------|--------------|
| 1 | **Report card block by financial arrears** | **Yes** | `apps/reports/services.py`: `student_has_financial_clearance()`; views block when `block_report_download_if_outstanding_balance` (default True). |
| 2 | **Arrears carry-forward on rollover** | **Yes** | `apps/finance/services.py`: `carry_forward_arrears()`; rollover form "Carry forward unpaid fees" (flag `carry_forward_arrears_on_rollover`). |
| 3 | **GCE Board export: CIN 9-digit, DATE_OF_BIRTH DD/MM/YYYY, EXAM_TYPE, MOMO_TRANS_ID** | **Yes** | `views_certification.py`: candidates.csv has CIN, DATE_OF_BIRTH (DD/MM/YYYY), EXAM_TYPE, MOMO_TRANS_ID, specialty_code. |
| 4 | **ITC/ATC pass rule (5 subjects, 2 Professional + 1 Related)** | **Yes** | `apps/reports/models.PromotionRule`: only `promotion_average` (e.g. 10/20). No Technical-specific “5 subjects, 2 professional” logic in promotion or rollover. |
| 5 | **Industrial attachment (Paper 3) mark → syncs to Sequence 6** | Partial | Evals has `practical_score` and workshop-related models; no explicit “Industrial Attachment” as Paper 3 that auto-syncs to a sequence score. |
| 6 | **Report card QR code + public verification URL** | No | No QR on report PDF; no public URL to verify authenticity against DB. |
| 7 | **Workshop inventory: block report/promotion if unreturned tool** | **Yes** | `StudentResourceReturn` exists (rollover can block on “outstanding returns”). Report download does not check unreturned resources/tools. |
| 8 | **Form 4 blocked from GCE registration (only Form 5 / Upper Sixth)** | **Yes** | `Classroom.gce_eligible`; bulk-add shows only GCE-eligible classrooms when any are marked. |
| 9 | **PTA vs Tuition vs Workshop fees (separate on invoice)** | Partial | `apps/finance`: Invoice, FeeItem, FeePlan. PTA/Workshop can be separate items; confirm generation and display match “PTA levy, Workshop fee, Tuition” split. |
| 10 | **Transport fee auto-appended to invoice (bus route)** | Unclear | No obvious “bus route” or transport fee auto-add on invoice in quick scan; needs verification. |
| 11 | **SMS to parent when report blocked (debt)** | No | Report download does not block by debt, so no “block + SMS” flow. After implementing (1), add optional SMS via `apps.communication`. |
| 12 | **Offline mark entry → cache → sync on reconnect** | Partial | `apps/evals`: `OfflineMarkEntry`, `offline_sync.py`, resolve conflict view. Backend exists; front-end may not use IndexedDB/LocalStorage for true offline cache and sync on reconnect. |
| 13 | **MoMo callback (webhook) + idempotency** | Yes | `apps/finance`: `payment_provider_webhook`, WebhookLog, idempotency in `security.py`. Implemented. |
| 14 | **Promotion by single average threshold (General)** | Yes | `PromotionRule.promotion_average`; rollover uses get_promotion_status. Implemented for single-threshold. |
| 15 | **Evals year lock (no edit after rollover)** | Yes | Evals views check academic year lock; edits forbidden after lock. Implemented. |

**Priority fixes from plan:** (1) Report card block by debt, (2) Arrears carry-forward, (3) GCE export format (Board columns + DD/MM/YYYY), (4) ITC/ATC pass logic if Technical stream is in scope — **all implemented**.

---

## Gaps (missing features / logic)

### GAP-001: Report card download not blocked by financial arrears
- **Severity:** Critical (Buea requirement: financial clearance before report card).
- **Where:** `apps/reports/views.py` — `parent_download_term_report`, `parent_download_annual_report`, and share-link flows.
- **Current:** No check for outstanding balance before generating/serving PDF.
- **Expected:** If student has outstanding balance (e.g. `Invoice` status not PAID or balance > 0), block download and show message: “Please clear fees at the Bursary” (or similar); optionally trigger SMS to parent via apps.communication.
- **Recommendation:** Add a helper (e.g. `student_has_financial_clearance(student, year, term)`) using apps.finance; call it before generating PDF and return 403 + message if not clear.

### GAP-002: Arrears not carried forward to next academic year
- **Severity:** High (year-on-year continuity).
- **Where:** `apps/accounts/views.py` — `rollover_year`; `apps/finance` (no “opening balance” or arrears carry-forward on rollover).
- **Current:** Rollover moves students and can lock source year; it does not create Opening Balance or carry unpaid fees into the new year in apps.finance.
- **Expected:** Unpaid fees from source year appear as Opening Balance / arrears for the target year for each student.
- **Recommendation:** After rollover, run a finance step: for each student with unpaid invoice in source year, create an Opening Balance entry or equivalent in target year (design with finance module maintainer).

---

## Bugs

*(Add as discovered: title, severity, steps, expected, actual, file/line if known.)*

- (none logged yet)

---

## Redundancies

*(Duplicate code, duplicate UI, dead code.)*

- (none logged yet)

---

## Improvements

*(UX, performance, clarity, or non-blocking enhancements.)*

- (none logged yet)

---

## Evals-specific

*(Marks, sequences, coefficients, approval, lock.)*

- (none logged yet)

---

## Report card–specific

*(PDF layout, content, bulk generation, share link, QR.)*

- (none logged yet)

---

## Finance & payment

*(Invoices, PTA/workshop split, MoMo callback, payroll.)*

- (none logged yet)

---

## GCE / EMIS / Rollover

*(Registration, export format, rollover logic, archive.)*

- (none logged yet)
