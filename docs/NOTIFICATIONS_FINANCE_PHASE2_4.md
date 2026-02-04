# Finance notifications (Phase 2 & Phase 4)

## Phase 2: Notifications & confirmations

| ID | Item | Implementation |
|----|------|----------------|
| 2.3 | New invoice issued notification | In-app notification to guardians with `can_view_finance` when an invoice is created (single create only; bulk create skips and uses Phase 4.1). Optional email via SiteSettings `finance_notify_new_invoice_email`. |
| 2.4 | Payment received notification | In-app notification when a payment is recorded (manual or receipt verification). Optional email via `finance_notify_payment_received_email`. |
| 2.5 | Optional email on receipt verification | Same as 2.4: when a receipt is verified and payment is created, guardians get in-app + optional email if the setting is on. |

### SiteSettings (Phase 2)

- **finance_notify_guardians_new_invoice** (default `True`) – Send in-app notification when a new invoice is issued.
- **finance_notify_guardians_payment_received** (default `True`) – Send in-app notification when a payment is recorded.
- **finance_notify_new_invoice_email** (default `False`) – Also send email for new invoice.
- **finance_notify_payment_received_email** (default `False`) – Also send email when payment is recorded.

### Code locations

- **apps/finance/notifications.py** – `notify_guardians_new_invoice`, `notify_guardians_payment_received`, `notify_guardians_new_invoices_bulk`.
- **apps/finance/signals.py** – Invoice `post_save` (when `created` and AR) calls `notify_guardians_new_invoice`; Payment `post_save` (when `created`) calls `notify_guardians_payment_received`.
- **apps/finance/services.py** – `create_fee_invoices` sets `_skip_new_invoice_notify` so bulk create does not send per-invoice notifications; use "Notify guardians" instead.

---

## Phase 4: Additional workflow & sync

| ID | Item | Implementation |
|----|------|----------------|
| 4.1 | Post–bulk invoice "Notify guardians" | After "Generate Fee Invoices", success message and **Notify guardians** button. POST to `finance:notify_guardians_new_invoices` sends in-app (and optional email) to guardians for the just-created invoice set. Invoice IDs stored in session until user clicks the button or navigates away. |
| 4.2 | Guardian → student contact sync on save | Implemented in **apps/people/signals.py**: `sync_student_parent_phone_from_guardian` updates `student.parent_phone` from `StudentGuardian.phone` when the latter is set and the former is empty. See docs/DATA_PARENT_CONTACT.md. |

### Code locations (4.1)

- **apps/finance/views.py** – `generate_fees` stores `finance_last_generated_invoice_ids` in session; `notify_guardians_new_invoices` (POST, staff only) reads session, calls `notify_guardians_new_invoices_bulk`, redirects to invoices.
- **templates/finance/generate_fees.html** – Success alert with "Notify guardians" button and "View invoices" link when `last_generated_count` > 0.
