# QA Audit: Student Enrollment & Fee Payment Modules

**Role:** Quality Assurance Lead  
**Scope:** Student enrollment flows and fee payment workflows  
**Focus:** Redundant data fields, workflow gaps (missing confirmations, empty states), consolidation and automation for 100% workflow efficiency

---

## 1. Redundant Data Fields

### 1.1 Parent/Guardian Contact Stored in Multiple Places

| Location | Fields | When populated |
|----------|--------|----------------|
| **StudentProfile** | `parent_phone` | Backend create form, onboarding wizard |
| **StudentGuardian** | `phone`, `email`, `whatsapp_number` | Onboarding wizard (all three); backend create does **not** set these |
| **User** (parent) | `email` | Both flows when parent account is created |

**Issue:** The same contact information is asked in two flows (backend “Create Student” and portal “Student Onboarding”) and stored in two places: on the student (`parent_phone`) and on the guardian link (`StudentGuardian.phone` / `.email`). When creating a guardian from the **backend** form, only `relationship` is set in `defaults`; `phone` and `email` are never copied from the form to `StudentGuardian`, so payment reminders and finance features may use the wrong or empty contact.

**Recommendation:** Use a single source of truth. Prefer **StudentGuardian** for contact (phone, email, whatsapp). On backend student create, when creating/linking the guardian, set `defaults={"relationship": ..., "phone": form.cleaned_data.get("parent_phone") or "", "email": parent_email or ""}` so guardian contact is always in sync. Optionally derive `StudentProfile.parent_phone` from the primary guardian’s phone (or sync on save) to avoid asking the same data twice in the UI.

### 1.2 Payment Reference Fields

| Model | Fields | Usage |
|-------|--------|--------|
| **Payment** | `reference` (80 chars), `external_reference` (128 chars) | In `create_payment_from_receipt`, both are set to the same value (transaction reference). |

**Issue:** Two fields store the same external reference; code and reports may use one or the other inconsistently.

**Recommendation:** Document or enforce a single semantic: e.g. `reference` = internal reference, `external_reference` = provider/transaction ID. If both are always the same, consider deprecating one and using the other everywhere, or clearly document when each is used.

### 1.3 Invoice Balance: Stored vs Computed

| Location | What | Note |
|----------|------|------|
| **Invoice** | `balance_amount` (denormalized) | Updated by `reconcile_balance()` and when payments are applied. |
| **Invoice** | `computed_balance` (property) | `total_amount - sum(payments)`. |

**Issue:** Two ways to get “balance”; risk of `balance_amount` being out of sync if code paths miss `reconcile_balance()`.

**Recommendation:** Already noted in model: migrate to using `computed_balance` everywhere and treat `balance_amount` as deprecated; ensure all payment apply paths call `reconcile_balance()` until migration is complete.

---

## 2. Workflow Gaps

### 2.1 Missing Confirmation / Notification Emails

| Event | Current behavior | Gap |
|--------|-------------------|-----|
| **Student created (backend)** | Message to staff: “Parent account created. Please send login credentials to {email}”. | No automated email to parent with sign-up link or temporary credentials. |
| **Student pre-registration (onboarding wizard)** | Success message only; parent account may be created. | No confirmation email to parent or student; no “next steps” or login instructions. |
| **Invoice issued (single or bulk)** | Invoices created; payment reminder is created by signal when due. | No “New invoice issued” email to guardians. Parents only hear about fees when reminders run. |
| **Bulk “Generate Fee Invoices”** | Success message and redirect. | No summary email to finance; no notification to affected parents that new invoices are available. |
| **Payment recorded manually (admin/finance)** | Payment saved; signal applies payment and updates invoice. | No notification to parent that payment was received and applied. |
| **Payment from receipt upload (verified)** | In-app notification sent to uploader (“Payment Verified”). | No optional email copy for receipt/audit. |

**Recommendation:** Add optional (configurable) emails: (1) Parent welcome/credentials or “complete registration” when student is created and parent email exists; (2) “New invoice” when an invoice is issued (or when bulk generation completes), to guardians with finance access; (3) “Payment received” when a payment is applied (manual or automated), with amount and invoice reference; (4) Optional email copy for receipt-upload verification. Use site/notification settings to enable/disable each.

### 2.2 Empty States Missing or Weak

| Page / Component | Current empty state | Gap |
|------------------|---------------------|-----|
| **Generate Fee Invoices** | Dropdown with “Select a plan”; no plans = empty dropdown, submit can fail. | No message like “No fee plans yet. Create a fee plan in Finance setup first.” or CTA to create a plan. |
| **Finance Dashboard – Recent Invoices** | Table row: “No invoices found.” | Acceptable; could use shared empty-state component with icon and short guidance. |
| **Finance Dashboard – Recent Payments** | Table row: “No payments recorded.” | Same as above. |
| **Invoices list (finance)** | “No invoices found.” or “Finance access is not enabled yet…” | OK; conditional message is good. |
| **Payments list (finance)** | “No payments recorded.” | OK. |
| **Parent Finance – Invoices** | “No invoices yet. Finance will publish them here when ready.” | Good. |
| **Parent Finance – Payment reminders** | “No active reminders. Finance will queue reminders once invoices become due.” | Good. |
| **Backend Student List** | “No students found. Create one” with link. | Good. |

**Recommendation:** Add an explicit empty state on **Generate Fee Invoices** when `plans` is empty: e.g. use `{% include 'components/dashboard_empty_state.html' %}` with title “No fee plans yet”, message “Create a fee plan (classroom/specialty and fee items) in Finance setup, then return here to generate invoices.” and action link to fee plan admin or finance dashboard. Optionally standardize other finance empty table states with the same component for consistency.

### 2.3 Data Consistency Gaps

| Scenario | Issue |
|----------|--------|
| **Backend Create Student + parent email** | Guardian link is created with `relationship` only; `StudentGuardian.phone` and `StudentGuardian.email` are not set from the form. So reminder/notification logic that uses guardian phone/email may miss the contact. |
| **Onboarding wizard** | Correctly sets both `student.parent_phone` and `StudentGuardian` (phone, email, whatsapp). Backend flow should mirror this. |

**Recommendation:** When creating or updating `StudentGuardian` from the backend student form, set `phone` and `email` from the form (and optionally whatsapp if you add it to the form). Consider a small helper that syncs `StudentProfile.parent_phone` from the primary guardian’s phone when the guardian is saved.

---

## 3. Checklist: Consolidate & Automate for 100% Workflow Efficiency

Use this list to close gaps and reduce redundancy. Tick when done.

### 3.1 Enrollment

- [ ] **ENR-1** Sync guardian contact on backend student create: when creating `StudentGuardian`, set `defaults` to include `phone=form.cleaned_data.get('parent_phone') or ''`, `email=parent_email or ''` (and optionally `whatsapp_number` if added to form).
- [ ] **ENR-2** Add optional “Parent welcome” email when a parent account is created (backend or onboarding): configurable in site/notification settings; include sign-up link or temporary password instructions.
- [ ] **ENR-3** Add optional “Pre-registration received” email after onboarding wizard: confirm student name, admission number (if any), and next steps (e.g. “Contact school to complete enrollment”).
- [ ] **ENR-4** Document or enforce single source for parent contact: prefer `StudentGuardian` (phone/email); ensure all reminder/notification code uses guardian contact and falls back to `StudentProfile.parent_phone` only if no guardian.

### 3.2 Fee / Invoice

- [ ] **FIN-1** Add optional “New invoice issued” notification to guardians (with finance access) when an invoice is created or when bulk generation completes: email and/or in-app; configurable.
- [ ] **FIN-2** Add empty state on Generate Fee Invoices when there are no fee plans: use shared empty-state component, message “No fee plans yet…”, and link to create fee plan or finance setup.
- [ ] **FIN-3** When bulk “Generate Fee Invoices” runs, add optional summary: e.g. “X invoices created for plan Y; notify guardians?” with a “Send new-invoice notifications” button or automatic send if configured.

### 3.3 Payment

- [ ] **PAY-1** Send “Payment received” notification when a payment is applied (manual or via receipt verification): to the invoice’s student guardians with finance access; include amount, invoice reference, and receipt/reference number; configurable.
- [ ] **PAY-2** Unify payment reference semantics: document or refactor so either `reference` or `external_reference` is the single “external transaction ID” and the other is internal-only or deprecated; update all reads/writes and reports.
- [ ] **PAY-3** Optional: add email copy when receipt upload is verified (in addition to in-app notification) for audit/parent records.

### 3.4 Data & UI Consistency

- [ ] **DATA-1** Ensure every code path that applies a payment (admin save, `apply_payment`, `create_payment_from_receipt`, webhooks) either calls `reconcile_balance()` on the invoice or uses only `computed_balance` and deprecate `balance_amount` in the long run.
- [ ] **DATA-2** Standardize empty states for finance tables (recent invoices, recent payments, payments list) using `dashboard_empty_state.html` or a shared partial for consistency and accessibility.
- [ ] **DATA-3** Add a simple “Guardian contact sync” on `StudentGuardian.save`: if this guardian is the only or primary guardian for the student, set `student.parent_phone = self.phone or student.parent_phone` (and save student) so one source of truth propagates.

---

## 4. Summary Table

| Category | Count | Priority |
|----------|-------|----------|
| Redundant fields (parent contact, payment reference, balance) | 3 | High (contact), Medium (reference, balance) |
| Missing confirmation/notification | 6 events | High |
| Empty state gaps | 1 (Generate Fees) | Medium |
| Data sync gaps (guardian contact on backend create) | 1 | High |

Implementing the checklist items above will remove redundancy, add missing confirmations and empty states, and align data and notifications so enrollment and fee payment workflows are consistent and efficient end to end.
