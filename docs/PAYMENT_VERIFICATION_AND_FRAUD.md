# Payment Receipt Verification & Fraud Handling

**Purpose:** How cash/bank receipt uploads are verified, how falsification is addressed, and how finance is notified.

---

## 1. How receipts are verified

### 1.1 Upload flow

- Parents/guardians upload payment proof (image/PDF) against an invoice via the portal or finance UI.
- The system stores the file in `PaymentProofUpload` and can trigger **synchronous or asynchronous** processing (Celery task: `finance.process_payment_receipt_upload`).

### 1.2 Verification steps

1. **Extraction**  
   Receipt data (amount, date, reference) is extracted using the method configured in Site Settings:
   - **Pattern:** Regex/keyword extraction from text (OCR or embedded text).
   - **OCR:** Optional OCR-based extraction when enabled.

2. **Invoice match**  
   Extracted amount (and optionally date/reference) is compared to the linked invoice with a configurable **amount tolerance** (`finance_receipt_amount_tolerance`). A **confidence** score is computed.

3. **Bank deposit verification (optional)**  
   If `finance_bank_verification_enabled` is on, the system tries to match the receipt to a **bank/MoMo statement entry** (by amount, date, reference) within a tolerance window (`finance_bank_verification_tolerance_days`). A match can increase confidence; a mismatch can decrease it.

4. **Fraud detection**  
   `ReceiptFraudDetector` runs on the upload and sets:
   - `fraud_risk_score` (0–100)
   - `fraud_flags` (list of risk indicators)
   - `is_suspicious` when the recommendation is "review" or "reject"
   - `flagged_at` when first marked suspicious

5. **Auto-apply decision**  
   A payment is **auto-created and applied** only when:
   - `finance_receipt_auto_apply_enabled` is True  
   - `finance_receipt_require_admin_approval` is False (or approval already given)  
   - Verification **matches** and **confidence** ≥ `finance_receipt_auto_apply_threshold`  
   - Fraud risk is not high (e.g. &lt; 70); high risk forces manual review regardless.

Otherwise the upload is left in **DISCREPANCY** (or **PENDING**) for manual review.

### 1.3 Dry-run

- `process_payment_receipt_upload_task(proof_upload_id, dry_run=True)` runs extraction, verification, and fraud detection but **does not** create a payment or send notifications. It updates verification data and notes on the upload and logs a DRY_RUN execution. Use it to test or preview results.

---

## 2. How falsification / fraud is addressed

- **Fraud detection:** Risk score and flags (e.g. date mismatch, duplicate reference, unusual amount) are stored and can force manual review even when verification would otherwise pass.
- **Manual review:** Uploads in DISCREPANCY or marked suspicious are reviewed by finance staff in the admin (Payment Proof Uploads). Staff can apply payment, reject, or request a new receipt.
- **Second approval (optional):** For large amounts, `finance_receipt_second_approval_threshold_xaf` can require a second approver before payment is applied.
- **Suspicious notifications:** When an upload is marked suspicious (high fraud risk or fraud flags), finance staff are notified via `_notify_finance_staff_suspicious_receipt` (in-app notification to configured finance users).

---

## 3. Finance notifications

- **When a receipt is suspicious:** Finance staff receive an in-app notification with fraud risk score, flags, and link to the upload (see above).
- **When a payment is applied (auto or manual):** The parent/guardian can be notified via the notification service (channels configurable; e.g. email, and optionally WhatsApp when enabled).
- **When there is a discrepancy:** The upload remains in the queue for finance; no automatic notification to the parent unless you add one (e.g. “Receipt received; under review”).

To add more notifications (e.g. “Payment applied” to finance, or “Discrepancy found” to parent), extend the task or admin actions and call the same notification service with the appropriate channels and templates.

---

## 4. References

- **Models:** `apps/finance/models.py` — `PaymentProofUpload`, `Payment`, `BankStatementEntry`
- **Task:** `apps/finance/tasks.py` — `process_payment_receipt_upload_task(proof_upload_id, dry_run=False)`
- **Verification:** `apps/finance/receipt_verification.py` — `ReceiptVerificationService`
- **Fraud:** `apps/finance/fraud_detection.py` — `ReceiptFraudDetector`
- **Site Settings:** Finance Automation → Receipt verification, bank verification, thresholds, approval
