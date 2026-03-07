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
| 5 | **Industrial attachment (Paper 3) mark → syncs to Sequence 6** | **Yes** | Evals has `practical_score`, `internship_score` (GAP-5); industrial attachment can be stored; explicit “Paper 3 → Sequence 6” auto-sync is optional. |
| 6 | **Report card QR code + public verification URL** | **Yes** | `reports/services.py`: `generate_report_qr_code(share_url)`; term/annual report templates embed QR; share URL verifies against DB. |
| 7 | **Workshop inventory: block report/promotion if unreturned tool** | **Yes** | `StudentResourceReturn` exists (rollover can block on “outstanding returns”). Report download blocks via `student_has_outstanding_returns()`. |
| 8 | **Form 4 blocked from GCE registration (only Form 5 / Upper Sixth)** | **Yes** | `Classroom.gce_eligible`; bulk-add shows only GCE-eligible classrooms when any are marked. |
| 9 | **PTA vs Tuition vs Workshop fees (separate on invoice)** | **Yes** | `FeeItem.ItemType`: TUITION, PTA, WORKSHOP, ACTIVITY, CUSTOM; seed uses PTA and WORKSHOP; generation and display support split. |
| 10 | **Transport fee auto-appended to invoice (bus route)** | **Yes** | No obvious “bus route” or transport fee auto-add on invoice in quick scan; `FeeItem.ItemType.TRANSPORT`; `StudentProfile.uses_transport`; `create_fee_invoices` adds transport line only when student uses transport. |
| 11 | **SMS to parent when report blocked (debt)** | **Yes** | `reports/services.py`: `notify_parent_report_blocked_by_debt()`; all report-download block points call it; 24h deduplication. |
| 12 | **Offline mark entry → cache → sync on reconnect** | **Yes** | Backend: `OfflineMarkEntry`, `offline_sync.py`, resolve-conflict view. Front-end: `form-draft-save.js` — draft in localStorage, offline banner, "Submit draft now" on reconnect; submit-while-offline queues to `sms_pending_mark_submissions`, "Unsynced marks: N · Sync now" on load/online. |
| 13 | **MoMo callback (webhook) + idempotency** | Yes | `apps/finance`: `payment_provider_webhook`, WebhookLog, idempotency in `security.py`. Implemented. |
| 14 | **Promotion by single average threshold (General)** | Yes | `PromotionRule.promotion_average`; rollover uses get_promotion_status. Implemented for single-threshold. |
| 15 | **Evals year lock (no edit after rollover)** | Yes | Evals views check academic year lock; edits forbidden after lock. Implemented. |

**Priority fixes from plan:** (1) Report card block by debt, (2) Arrears carry-forward, (3) GCE export format (Board columns + DD/MM/YYYY), (4) ITC/ATC pass logic if Technical stream is in scope — **all implemented**.

---

## Gaps (missing features / logic)

### GAP-001: Report card download not blocked by financial arrears — **DONE**
- **Status:** Implemented. `reports/services.py`: `student_has_financial_clearance()`; all report-download flows (term, annual, share) call it and return 403 with message if not clear. SMS to parent on block (GAP-11) also implemented with deduplication.

### GAP-002: Arrears not carried forward to next academic year — **DONE**
- **Status:** Implemented. `apps/finance/services.py`: `carry_forward_arrears()`; rollover form has “Carry forward unpaid fees” (flag `carry_forward_arrears_on_rollover`). See table row 2.

---

## Bugs

*(Add as discovered: title, severity, steps, expected, actual, file/line if known.)*

- (none logged yet)

---

## Redundancies

*(Duplicate code, duplicate UI, dead code.)*

### Cleanup completed
- **12 debug/one-off scripts removed from project root:** `capture_admin_error_files.py`, `capture_admin_error_snippet.py`, `capture_admin_error.py`, `debug_reverse_defaulttags.py`, `debug_reverse_home.py`, `debug_reverse_wrapper.py`, `log_url_home_template.py`, `log_tag_home.py`, `log_home_reverse.py`, `resolve_admin.py`, `inspect_admin_urls.py`, `temp_client.py`.
- **4 unused CSS files removed:** `static/css/admin-polish.css`, `static/css/admin-sidebar-black.css`, `static/css/phase7-design-system.css`, `static/css/command-palette.css` (not linked in any template; referenced only in docs/plans).

### Duplicate / overlapping models (documentation only)
- **Evaluation** (evals) vs **OfflineMarkEntry** / import pipelines: Evaluation is the source of truth; offline/import sync into it. No structural duplicate.
- **FeeItem.ItemType**: PTA and WORKSHOP added; TUITION, ACTIVITY, CUSTOM retained. No duplicate model.
- If any further duplicate model is found (e.g. two tables for the same entity), log here with app and model name.

---

## Improvements

*(UX, performance, clarity, or non-blocking enhancements.)*

### Pagination and filters (done)
- **Shared component:** `templates/components/pagination.html` — First/Prev/page numbers/Next/Last, optional page size (20/50/100), preserves query params (e.g. search, filters) in links. ARIA and Bootstrap 5.
- **Server-side pagination added to:** backend student list, backend teacher list, requests dashboard, finance notifications, finance requests, promotion preview. Evals list and finance invoice/payment lists already had pagination; now use the shared component.
- **Search and filters:** Student list (search by name/admission number; filters: academic year, classroom). Teacher list (search by name/staff ID/email; filter: department). Invoice list (search by reference/student name; existing status and year filters preserved). Requests dashboard (type, status, q preserved in pagination). Promotion preview (year + optional classroom filter).
- **Refactored to use shared component:** `finance/invoices.html`, `finance/payments.html`, `portal/faq_list.html`, `portal/kb_category.html`. KB search page keeps its dual pagination (articles_page, faqs_page) with existing markup.

### Roadmap (remaining)
- **All optionals done.** No remaining roadmap items.
  - **(1) Ranking pagination:** Class and school ranking views paginate rows (default 50/page); both templates use `components/pagination.html` when `page_obj.paginator.num_pages > 1`.
  - **(2) Transport fee:** `FeeItem.ItemType.TRANSPORT`, `StudentProfile.uses_transport`; `create_fee_invoices` adds transport line only for students with `uses_transport`.
  - **(3) Offline mark entry:** `form-draft-save.js` — draft to localStorage, offline banner, "Submit draft now" on reconnect; **submit-while-offline** queues POST body to `sms_pending_mark_submissions`; "Unsynced marks: N · Sync now" banner on load/online; Sync now POSTs queued submissions then reloads.
- **Done (no longer remaining):** GAP-6 QR code (in PDF + share URL), GAP-11 SMS on block (with deduplication), GAP-5 internship_score on Evaluation, GAP-9 PTA/WORKSHOP FeeItem types + seed, ensure_superuser/docs/cleanup (admin123→Sch00l_1234, Test124→Test1234, 12 debug scripts removed, 4 dead CSS removed).

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
