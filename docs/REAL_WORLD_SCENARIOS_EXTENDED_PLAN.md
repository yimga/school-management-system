# Real-World Scenarios – Extended Plan

This document adds **additional real-world examples** beyond the existing [Real-World Scenarios & Flexibility Guide](REAL_WORLD_SCENARIOS_AND_FLEXIBILITY.md), with how the system handles them today and what to plan or configure.

---

## 1. Finance & Payments

### 1.1 Overpayment (Parent Pays More Than Invoice Balance)

**Scenario**: Invoice balance is 45,000 XAF; parent pays 50,000 XAF and uploads receipt.

**Current**: `Payment.clean()` blocks saving a payment that exceeds remaining balance, so overpayment cannot be recorded as a single payment against that invoice.

**Plan**:
- **Option A**: Allow recording up to a small tolerance (e.g. 1% or fixed XAF) as “overpayment”; treat invoice as PAID and carry forward excess as credit or separate “credit note” for next invoice.
- **Option B**: Keep strict validation; finance records payment for 45,000 XAF and creates a **RefundRequest** (reason: overpayment) for 5,000 XAF, or applies 5,000 XAF to another invoice manually.
- **Recommendation**: Implement Option A with a configurable overpayment tolerance (SiteSettings: `finance_overpayment_tolerance_xaf` or `finance_overpayment_tolerance_percent`). When within tolerance, create one Payment for balance, mark invoice PAID, and create a “credit” or RefundRequest for the excess.

**Config**: Add `finance_overpayment_handling` = `reject` | `allow_with_refund` | `allow_as_credit`.

---

### 1.2 Refund After Payment (Duplicate, Wrong Amount, Parent Request)

**Scenario**: Payment was applied; later parent or finance discovers duplicate payment, wrong amount, or parent requests refund.

**Current**: `RefundRequest` model exists with reasons (duplicate, incorrect_amount, student_request, overpayment, compliance, other). Workflow: request → approve → process.

**Plan**:
- Ensure refund approval notifies parent and updates invoice balance (reverse payment effect or mark payment as refunded).
- Link refund to original Payment; when processed, create Transaction (type=refund) and optionally adjust invoice status back to PARTIAL/ISSUED if full refund.
- Document in admin: “After approving refund, process via bank/MoMo manually and mark RefundRequest as processed.”

**Config**: Already supported; add SiteSettings: `finance_refund_requires_approval` (default True), `finance_refund_approvers` (group name).

---

### 1.3 Invoice Voided or Cancelled After Partial Payment

**Scenario**: Invoice was partially paid; school then voids the invoice (e.g. student withdrew, fee structure changed).

**Current**: Invoice has status VOID. Need to ensure reminders stop and any remaining balance is handled.

**Plan**:
- When invoice status is set to VOID:
  - Deactivate linked PaymentReminder (if any).
  - Optionally create RefundRequest for already-paid amount, or leave as credit for future use (configurable).
- Add validation: “Voiding invoice with payments: [ ] Refund payments [ ] Convert to credit [ ] Void only (no refund).”

**Config**: `finance_void_invoice_with_payments` = `allow_refund` | `allow_credit_only` | `block_void`.

---

### 1.4 Receipt Uploaded for Wrong Invoice (Same Student)

**Scenario**: Parent has two invoices (e.g. tuition + exam fee); uploads receipt for exam fee but selects tuition invoice.

**Current**: Receipt is tied to the invoice the parent selected. Verification compares amount/reference to that invoice; if mismatch → DISCREPANCY.

**Plan**:
- In admin “Payment Proof Upload” review: add action “Reassign to another invoice” (same student). Re-run verification against the new invoice.
- Optional: when amount matches another open invoice for same student, suggest “Possible wrong invoice?” in verification notes.

**Config**: No new setting; admin action only.

---

### 1.5 Receipt for Different Child (Sibling / Wrong Student)

**Scenario**: Parent pays for Child A but uploads receipt against Child B’s invoice.

**Current**: Receipt is tied to the invoice (and thus student) chosen at upload. No automatic cross-student match.

**Plan**:
- Allow finance in admin to “Reassign to another invoice” with optional filter “same guardian” so they can move receipt to the correct child’s invoice.
- Fraud detector could add a soft flag if same guardian has another unpaid invoice with matching amount (e.g. “possible_sibling_swap”).

**Config**: Admin action + optional SiteSettings: `finance_receipt_allow_reassign_different_student` (default True for staff).

---

### 1.6 One Payment for Multiple Invoices (Siblings or Multi-Item)

**Scenario**: Parent pays 100,000 XAF once for two children (50,000 each) or for tuition + exam in one transfer.

**Current**: One payment is typically tied to one invoice. Splitting one payment across multiple invoices is not standard.

**Plan**:
- **Option A**: Finance records two separate Payment records (50,000 each) with same reference/receipt, both linked to same receipt file or proof upload. Manual process.
- **Option B**: Introduce “batch payment” or “split payment”: one receipt/proof upload, finance assigns portions to multiple invoices; system creates multiple Payment records and applies each.
- **Recommendation**: Short term use Option A (manual). Later add “Split payment” admin action: select one proof upload, specify amounts per invoice, system creates multiple Payments and applies.

**Config**: Future: `finance_allow_split_receipt_to_multiple_invoices` (default False until feature exists).

---

## 2. Communication & Reminders

### 2.1 Guardian Has No Email or Phone

**Scenario**: Guardian has no email and no phone; reminders cannot be sent.

**Current**: Reminder task sends to email/SMS/WhatsApp per channel; if no address, that channel is skipped. No fallback.

**Plan**:
- In reminder run, log “No contact for guardian X, invoice Y” (already partially there). Optionally create an in-app notification or “pending contact” list for admin.
- SiteSettings: “When no contact: [ ] Skip reminder only [ ] Create task for staff to contact guardian [ ] Block invoice issuance until contact added.”

**Config**: `finance_reminder_no_contact_action` = `skip` | `create_task` | `warn_only`.

---

### 2.2 SMS/Email/WhatsApp Fails (Network, Invalid Number, Provider Down)

**Scenario**: Reminder is sent but provider fails (timeout, invalid number, rate limit).

**Current**: `PaymentReminderLog` stores status (SENT/FAILED) and note. Email uses `fail_silently=True`. SMS/WhatsApp may not always log failure.

**Plan**:
- Ensure all channels log FAILED with reason (e.g. “Twilio: invalid number”, “SMTP timeout”). Retry: optional retry_task for “last_sent_at older than X, status FAILED” with exponential backoff.
- Dashboard or report: “Reminders failed in last 7 days” for follow-up.
- SiteSettings: `finance_reminder_retry_failed_hours` (e.g. 24) and `finance_reminder_max_retries` (e.g. 2).

**Config**: Already have logs; add retry task and optional report.

---

### 2.3 Parent Says “I Never Received the Reminder”

**Scenario**: Parent claims they did not get the reminder; due date passed.

**Current**: PaymentReminderLog stores sent_at, channel, note (e.g. “Email sent to x@y.com”).

**Plan**:
- In parent portal or admin: “Reminder history” for invoice showing last_sent_at, channel, and note (mask email/phone for privacy). So staff can say “We sent email on X to y@z.com.”
- Optional: “Resend reminder” button (creates new send with same template, logged).

**Config**: No new setting; UI for reminder history + resend.

---

### 2.4 Reminder Sent on Public Holiday or Non-Business Day

**Scenario**: Due date is Monday; reminder “3 days before” falls on Saturday. Bank/MoMo may be slower; school office closed.

**Current**: Reminder schedule is by “days before due date”, not by business days.

**Plan**:
- Optional: “Use business days only” (SiteSettings: `finance_reminder_business_days_only`). If True, compute next_send_at using a calendar that skips weekends (and optionally a list of public holidays).
- Store public holidays in RegionConfig or SiteSettings (e.g. JSON list of dates) for Cameroon.

**Config**: `finance_reminder_business_days_only`, `finance_public_holidays` (JSON dates or reference to calendar).

---

## 3. Student Lifecycle & Academic

### 3.1 Student Withdraws Mid-Term (With Outstanding Balance)

**Scenario**: Student is marked withdrawn; they have unpaid or partially paid invoices.

**Current**: Invoice is tied to student. Student can be set inactive/withdrawn. Reminders may still run if reminder is active.

**Plan**:
- When student status is set to “Withdrawn” (or equivalent): (1) Deactivate all PaymentReminders for their invoices. (2) Optionally auto-void or mark invoices as “closed – student withdrawn” (custom status or note). (3) Report: “Outstanding balance by withdrawn students” for follow-up (refund or waiver policy).
- SiteSettings: `finance_on_student_withdrawal` = `stop_reminders_only` | `stop_reminders_and_mark_invoices` | `no_auto_change`.

**Config**: `finance_on_student_withdrawal`.

---

### 3.2 Student Withdraws After Full Payment (Refund or Credit)

**Scenario**: Parent paid full term fee; student withdraws before term end. School policy: partial refund.

**Current**: RefundRequest exists; no automatic link to “withdrawal”.

**Plan**:
- On withdrawal, if there are paid invoices, show admin a warning: “Student has paid invoices. Create refund request?” with link to create RefundRequest (reason: student_request or other).
- Optional: workflow “Withdrawal + refund request” in one form (amount, reason, approval path).

**Config**: Optional `finance_prompt_refund_on_withdrawal` (default True).

---

### 3.3 Graduate with Unpaid Balance

**Scenario**: Student graduates but has an old unpaid invoice (e.g. activity fee).

**Current**: Rollover/graduation sets status to Alumni, is_active False. Invoices remain.

**Plan**:
- Report: “Graduated / alumni with outstanding balance.” Do not auto-waive; let finance decide (waive, pursue, or write off).
- Optional: when marking student as graduated, block if outstanding balance and SiteSettings `block_graduation_if_outstanding` is True (similar to existing “block promotion if outstanding returns”).

**Config**: `finance_block_graduation_if_outstanding` (default False).

---

### 3.4 Fee Waiver / Scholarship / Discount After Invoice Issued

**Scenario**: Invoice already issued; later school grants waiver or discount.

**Current**: DynamicPricingRule and FeePlan exist. Adjustments at issue time are supported; post-issue waiver less so.

**Plan**:
- Support “invoice adjustment”: negative line item or “waiver” amount on invoice, reducing total and balance. Or: create a “Credit” that applies to the invoice (like a payment but with type=waiver). Recalculate balance and status.
- Admin: “Apply waiver to invoice” (amount + reason); system updates invoice total/balance and stops or adjusts reminders.

**Config**: `finance_allow_post_issue_waiver` (default True), optional approval workflow.

---

### 3.5 Sibling Discount (Multiple Children, One Guardian)

**Scenario**: School offers 10% off for second child; parent has two children.

**Current**: DynamicPricingRule has SIBLING_COUNT condition; applies at rule evaluation time. Ensure fee generation uses it.

**Plan**:
- Verify that when creating fee invoices, DynamicPricingRule with SIBLING_COUNT is applied so second child’s invoice is reduced. Document how to configure (min_siblings, discount %).
- If invoices are created before sibling link is set, add admin action “Recalculate invoice with current rules” to apply discount retroactively.

**Config**: Already in rule parameters; ensure FeePlan/creation path applies rules.

---

## 4. Infrastructure & Technical

### 4.1 Power or Internet Outage During Receipt Upload

**Scenario**: Parent submits receipt; request times out or fails mid-upload.

**Current**: Front-end may show error; backend may or may not have created PaymentProofUpload (partial save).

**Plan**:
- Idempotent upload: use a client-generated idempotency key (e.g. hash of file + invoice_id + user_id). If same key received again, return “already received” and same proof_upload_id. Prevents duplicate on retry.
- Show clear message: “If payment was deducted but you see an error, do not pay again. Contact finance with your transaction reference.”

**Config**: Optional `finance_receipt_idempotency_window_minutes` (e.g. 10).

---

### 4.2 File Too Large or Unsupported File Type

**Scenario**: Parent uploads 10 MB file or .exe; validation rejects.

**Current**: Validators (e.g. `validate_receipt_file`, `validate_file_size_2mb`) should reject invalid types/sizes.

**Plan**:
- Return clear error: “File must be PDF or image (JPG, PNG), max 5 MB. Please compress or take a clear photo.”
- SiteSettings: `finance_receipt_max_size_mb`, `finance_receipt_allowed_extensions` (default: pdf, jpg, jpeg, png).

**Config**: Already partially there; centralise limits in settings.

---

### 4.3 Double Submit (Parent Clicks “Upload” Twice)

**Scenario**: Two identical uploads created for same invoice.

**Current**: Fraud detector has duplicate file hash and duplicate transaction reference; flags duplicate. Second upload can be flagged.

**Plan**:
- Front-end: disable submit button after first click; show “Uploading…”.
- Backend: idempotency key (see 4.1) or short-window duplicate check (same invoice + same user + same file hash within 5 minutes) → return existing proof_upload and “Already received.”

**Config**: Same as 4.1.

---

### 4.4 Bank or MoMo Provider Down (Cameroon)

**Scenario**: MTN MoMo or Orange Money is down; parents cannot pay; receipts will come later.

**Current**: No specific handling.

**Plan**:
- Optional “outage” notice in parent portal / finance page: “MTN MoMo is currently experiencing issues. You can pay via bank transfer or cash. Receipts can be uploaded later.”
- SiteSettings: `finance_outage_message` (rich text or plain), `finance_outage_active` (boolean). When active, show message and optionally extend due date for “affected” payment method (optional, more complex).

**Config**: `finance_outage_active`, `finance_outage_message`, optional `finance_outage_extends_due_days`.

---

## 5. Time & Calendar

### 5.1 Due Date on Weekend or Public Holiday

**Scenario**: Due date falls on Sunday; banks closed; parents expect grace until Monday.

**Current**: Due date is a date; no automatic “next business day” logic.

**Plan**:
- Optional: when computing “overdue”, use “effective due date” = first business day on or after due_date (skip weekends + public holidays). Display: “Due by X (effective Y because of holiday).”
- SiteSettings: `finance_effective_due_date_business_days`, `finance_public_holidays` (see 2.4).

**Config**: Same as 2.4.

---

### 5.2 Timezone (Cameroon vs Server UTC)

**Scenario**: Receipt date is “Feb 2” in Cameroon; server is UTC; cutoff at midnight UTC might shift “Feb 2” to “Feb 1”.

**Current**: Django timezone handling; receipt_date on PaymentProofUpload is DateField.

**Plan**:
- Store and compare dates in school timezone (e.g. Africa/Douala). Use `timezone.localtime()` when deriving “today” for receipt date validation and bank verification windows. Already recommended in fraud/verification code.

**Config**: Ensure `USE_TZ=True` and `TIME_ZONE` or RegionConfig timezone is set for Cameroon.

---

## 6. Compliance & Audit

### 6.1 Audit Trail for Manual Overrides

**Scenario**: Finance approves a receipt that failed auto-verification or overrides fraud flag. Auditor asks “who approved and why?”

**Current**: PaymentProofUpload has `verified_by`, `verified_at`; optional notes.

**Plan**:
- Ensure all “approve”/“reject” actions set verified_by, verified_at, and a short verification_notes (e.g. “Approved after checking bank statement manually. Ref: TXN123.”). Consider Django audit log or simple AuditLog model: action, model, object_id, user, timestamp, reason.

**Config**: No new setting; enforce required “reason” on override actions.

---

### 6.2 Year-End or Period Close with Pending Receipts

**Scenario**: End of financial year; some receipts still in “pending” or “discrepancy”.

**Current**: No formal “close period” that blocks new actions.

**Plan**:
- Report: “Pending receipt uploads older than X days” for period close. Optional “Close period” that: (1) Locks invoices before date X from new payment application (or only allows with override), (2) Exports audit trail. Complex; start with report only, then optional lock.

**Config**: Optional `finance_period_close_date`, `finance_period_close_blocks_payment_application` (default False).

---

## 7. Multi-Region / Multi-Campus

### 7.1 Different Fee Schedules or Payment Methods Per Region/Campus

**Scenario**: Campus A accepts only bank; Campus B accepts MoMo and cash.

**Current**: ComplianceProfile and BankAccount can be region-specific; payment methods can be filtered by profile.

**Plan**:
- Ensure fee generation and reminder “payment instructions” use region/campus so only relevant bank/MoMo accounts and methods are shown. Already partially done via BankAccount.region and invoice profile.
- Document: “Per-region bank accounts and payment methods” in admin.

**Config**: Already in place; document and test.

---

### 7.2 One Guardian, Children in Different Campuses

**Scenario**: Parent has one child in Campus A and one in Campus B; different fee amounts and methods.

**Current**: Invoices are per student; reminders are per invoice; payment instructions can differ by invoice profile/region.

**Plan**:
- No change needed if each invoice has correct profile/region; reminders will show the right instructions per invoice. Ensure parent portal groups by student and shows correct “Pay” instructions per invoice.

**Config**: None.

---

## 8. Staff & Delegation

### 8.1 Bursar or Approver on Leave

**Scenario**: Only one person can approve refunds/receipts; they are unavailable.

**Current**: Approval is often by group (e.g. Finance, Bursar). No delegation or “deputy” concept.

**Plan**:
- Use Django groups: add “Deputy Bursar” or “Finance Approver” and assign temporarily. Optional: “Approval delegation” in user profile (e.g. “User A delegates to User B from date X to Y”) used by approval checks. Simpler: second group “Finance Approver” that can approve when Bursar is away.

**Config**: Document group-based approval; optional delegation table later.

---

### 8.2 High-Value Receipt Requires Second Approval

**Scenario**: School policy: receipts above 500,000 XAF need two approvers.

**Current**: Single approval in admin (approve/reject).

**Plan**:
- Add “two-step approval” for receipts above threshold: first approval moves to “Approved – Pending second approval”; second approver converts to VERIFIED and creates Payment. SiteSettings: `finance_receipt_second_approval_threshold_xaf`, workflow state “pending_second_approval”.

**Config**: `finance_receipt_second_approval_threshold_xaf` (0 = disabled).

---

## 9. Cameroon-Specific

### 9.1 Receipt in French or Mixed Language

**Scenario**: Receipt text is in French (e.g. “Montant”, “Référence”); OCR or pattern extraction may miss.

**Current**: ReceiptVerificationService uses pattern matching; may have English-centric patterns.

**Plan**:
- Add French patterns/keywords for amount, date, reference (e.g. “Montant”, “Total”, “Date”, “Réf”, “Référence”). Use same extraction logic with alternate regex. SiteSettings: `finance_receipt_verification_locales` = `en` | `fr` | `en,fr`.

**Config**: `finance_receipt_verification_locales`.

---

### 9.2 Cash Shortage (School Cannot Give Change)

**Scenario**: Parent pays 55,000 XAF in cash for 52,000 XAF invoice; office has no change.

**Current**: Payment must equal balance (or within tolerance). Overpayment handling (1.1) can treat excess as refund/credit.

**Plan**:
- Allow “round up” or “no change” policy: accept 55,000 XAF as payment for 52,000 XAF invoice; 3,000 XAF as donation or credit. Implement as overpayment-with-credit (see 1.1). Optional note on payment: “Accepted 55,000 (no change); 3,000 as credit.”

**Config**: Same as overpayment tolerance; add note in admin.

---

### 9.3 Network Failures (MTN/Orange Intermittent)

**Scenario**: Intermittent failures; parent pays but confirmation is delayed; receipt appears next day.

**Current**: Delayed bank/MoMo verification is handled by retry_bank_verification_task and tolerance days.

**Plan**:
- Reuse “retry verification” and “tolerance days” (e.g. 7–45 days). No extra logic; document for staff: “If MoMo was down, upload statement when available and run re-verify.”

**Config**: Already covered in REAL_WORLD_SCENARIOS_AND_FLEXIBILITY.md.

---

## 10. Summary Table

| # | Scenario | Current handling | Plan / config |
|---|----------|------------------|----------------|
| 1.1 | Overpayment | Blocked by validation | Tolerance + credit/refund; config |
| 1.2 | Refund | RefundRequest exists | Ensure invoice update + optional approvers |
| 1.3 | Invoice void with payments | VOID status | Stop reminders; optional refund/credit choice |
| 1.4 | Wrong invoice (same student) | DISCREPANCY | Admin “Reassign to invoice” |
| 1.5 | Wrong student (sibling) | Tied to chosen invoice | Admin reassign; optional fraud hint |
| 1.6 | One payment, multiple invoices | One payment per invoice | Manual split; later “split payment” action |
| 2.1 | No email/phone | Skip channel | Log; optional task; config |
| 2.2 | Send failure | Log FAILED | Retry task + report |
| 2.3 | “I didn’t get reminder” | Logs exist | Reminder history + resend |
| 2.4 | Reminder on holiday | Calendar-agnostic | Business days + holidays |
| 3.1 | Withdrawal with balance | No auto | Stop reminders; optional mark invoices |
| 3.2 | Withdrawal after payment | Manual refund | Prompt refund on withdrawal |
| 3.3 | Graduate with balance | No block | Report; optional block graduation |
| 3.4 | Waiver after issue | Limited | Invoice adjustment / credit |
| 3.5 | Sibling discount | Rule exists | Verify application; recalc action |
| 4.1 | Upload timeout | Possible duplicate | Idempotency key |
| 4.2 | File size/type | Validators | Clear message; config limits |
| 4.3 | Double submit | Duplicate detection | Idempotency + disable button |
| 4.4 | Provider down | None | Outage message + optional grace |
| 5.1 | Due date weekend/holiday | None | Effective due date (business days) |
| 5.2 | Timezone | DateField | Use school timezone consistently |
| 6.1 | Audit override | verified_by/at | Require reason; audit log |
| 6.2 | Year-end pending | None | Report; optional period lock |
| 7.1 | Per-region methods | Region on accounts | Document and test |
| 7.2 | Guardian multi-campus | Per-invoice | No change |
| 8.1 | Approver away | Groups | Delegation or second group |
| 8.2 | High-value two approvers | Single | Threshold + second approval |
| 9.1 | French receipt | Patterns | French keywords/locales |
| 9.2 | No change (cash) | Overpayment | Tolerance + credit note |
| 9.3 | MoMo delayed | Retry + tolerance | Already planned |

---

## Implementation Priority (Suggested)

**Phase 1 – Quick wins (config + small code)**  
- 2.1 No contact action, 2.3 Reminder history + resend  
- 4.2 File size/type message and config  
- 6.1 Audit reason on override  

**Phase 2 – Important for operations**  
- 1.1 Overpayment tolerance + credit/refund  
- 1.3 Void invoice behaviour (stop reminders, option)  
- 1.4 Admin “Reassign to invoice”  
- 2.2 Retry failed reminders + report  
- 3.1 Stop reminders on withdrawal  
- 4.1 / 4.3 Idempotency and double-submit  

**Phase 3 – Policy and compliance**  
- 2.4 Business days and holidays  
- 5.1 Effective due date  
- 3.4 Post-issue waiver  
- 6.2 Period close report  
- 8.2 Second approval threshold  

**Phase 4 – Cameroon and edge cases**  
- 9.1 French receipt patterns  
- 4.4 Outage message  
- 1.6 Split payment (if needed)  
- 8.1 Delegation (if needed)  

This extended plan keeps your existing behaviour where it’s sufficient and adds concrete, configurable handling for each real-world case.
