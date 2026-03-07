# Payment Receipt Upload & Automated Verification Plan

**Goal**: Enable parents to upload payment receipts (cash/bank), automatically verify them, and automatically apply payments to their children's accounts.

**Current State**: 
- ✅ Invoice model has `payment_proof` field
- ✅ Payment model has `receipt_file` field
- ✅ Payment application logic exists (`apply_payment()`)
- ❌ No parent portal upload interface
- ❌ No automated receipt verification
- ❌ No automatic payment creation from receipts

---

## Current Payment Flow

### Mobile Money (Automated)
1. Parent pays via MTN MoMo/Orange Money
2. Payment gateway sends webhook
3. System creates `Payment` record
4. Signal automatically calls `apply_payment()`
5. Invoice status updated to PAID/PARTIAL

### Cash/Bank (Manual - Current)
1. Parent pays cash/bank transfer
2. Parent sends receipt to school (WhatsApp/email)
3. **Admin manually creates Payment record**
4. Admin uploads receipt file
5. Admin verifies amount matches invoice
6. Admin saves → Signal applies payment

### Cash/Bank (Automated - Target)
1. Parent pays cash/bank transfer
2. **Parent uploads receipt in portal**
3. **System extracts amount/reference from receipt (OCR)**
4. **System matches receipt to invoice**
5. **System creates Payment record automatically**
6. **System verifies amount matches**
7. **If verified → Auto-apply payment**
8. **If discrepancy → Flag for admin review**

---

## Implementation Plan

### Phase 1: Parent Portal Receipt Upload

**1.1 Add Receipt Upload View**
- **Location**: `apps/portal/views.py` or `apps/finance/views.py`
- **URL**: `/portal/parent/invoices/<invoice_id>/upload-receipt/`
- **Method**: POST with file upload
- **Access**: Parents (guardians) only, for their children's invoices

**Features**:
- Upload receipt file (PDF/image)
- Enter transaction reference (optional, can be extracted)
- Enter payment amount (optional, can be extracted)
- Select payment method (CASH, BANK)
- Add notes (optional)

**1.2 Update Parent Finance Template**
- Add "Upload Payment Receipt" button on invoice detail page
- Show upload form modal or separate page
- Display uploaded receipts with status

---

### Phase 2: Receipt Verification Service

**2.1 Create Receipt Verification Service**
- **Location**: `apps/finance/receipt_verification.py`
- **Purpose**: Extract data from receipt images/PDFs

**Methods**:
```python
class ReceiptVerificationService:
    def extract_receipt_data(receipt_file) -> dict:
        """
        Extract amount, reference, date from receipt.
        Returns: {
            "amount": Decimal,
            "reference": str,
            "date": date,
            "confidence": float,  # 0.0-1.0
            "extraction_method": "ocr" | "pattern" | "manual"
        }
        """
    
    def verify_receipt_match(receipt_data, invoice) -> dict:
        """
        Verify receipt matches invoice.
        Returns: {
            "matches": bool,
            "amount_match": bool,
            "reference_match": bool,
            "confidence": float,
            "discrepancies": list
        }
        """
```

**2.2 OCR Integration (Optional)**
- **Option A**: Use Tesseract OCR (free, open-source)
- **Option B**: Use cloud OCR (Google Vision API, AWS Textract) - paid
- **Option C**: Pattern matching (regex) for common receipt formats - free
- **Recommendation**: Start with Option C (pattern matching), add OCR later

**Pattern Matching Strategy**:
- Extract amount: Look for currency symbols + numbers
- Extract reference: Look for transaction IDs, reference numbers
- Extract date: Look for date patterns
- Common formats: MTN MoMo receipts, bank transfer confirmations, cash receipts

---

### Phase 3: Automated Payment Creation & Application

**3.1 Create Payment from Receipt**
- **Location**: `apps/finance/services.py`
- **Function**: `create_payment_from_receipt(invoice, receipt_file, method, verification_data)`

**Workflow**:
1. Upload receipt → Create `PaymentProofUpload` record (status: PENDING)
2. Extract receipt data (OCR/pattern matching)
3. Verify against invoice (amount, reference)
4. If verified → Create `Payment` record → Auto-apply
5. If discrepancy → Flag for admin review

**3.2 PaymentProofUpload Model**
```python
class PaymentProofUpload(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Verification"
        VERIFYING = "VERIFYING", "Verifying"
        VERIFIED = "VERIFIED", "Verified - Payment Applied"
        DISCREPANCY = "DISCREPANCY", "Discrepancy - Needs Review"
        REJECTED = "REJECTED", "Rejected"
    
    invoice = ForeignKey(Invoice)
    uploaded_by = ForeignKey(User)  # Parent/guardian
    receipt_file = FileField(...)
    payment_method = CharField(...)  # CASH, BANK
    transaction_reference = CharField(...)
    uploaded_amount = DecimalField(...)  # Amount from receipt
    verification_data = JSONField(...)  # Extracted data
    verification_confidence = FloatField(...)
    status = CharField(choices=Status.choices, default=Status.PENDING)
    payment = ForeignKey(Payment, null=True)  # Created payment
    verified_by = ForeignKey(User, null=True)  # Admin if manual verification
    verification_notes = TextField(...)
    created_at = DateTimeField(auto_now_add=True)
    verified_at = DateTimeField(null=True)
```

---

### Phase 4: Integration with Automation

**4.1 Automated Receipt Processing Task**
- **Location**: `apps/finance/tasks.py`
- **Celery Task**: `process_payment_receipt_uploads_task()`

**Workflow**:
1. Find pending `PaymentProofUpload` records
2. Extract receipt data (OCR/pattern matching)
3. Verify against invoice
4. If verified → Create Payment → Auto-apply
5. If discrepancy → Flag for admin review
6. Send notification to parent (verified/rejected)

**4.2 SiteSettings Configuration**
```python
# Receipt Verification
finance_receipt_auto_verify_enabled = BooleanField(default=True)
finance_receipt_verification_method = CharField(choices=[
    ("pattern", "Pattern Matching (Free)"),
    ("ocr_tesseract", "Tesseract OCR (Free)"),
    ("ocr_cloud", "Cloud OCR (Paid)"),
], default="pattern")
finance_receipt_auto_apply_threshold = FloatField(
    default=0.9,
    help_text="Confidence threshold (0.0-1.0) for auto-applying payments"
)
finance_receipt_require_admin_approval = BooleanField(
    default=False,
    help_text="Require admin approval even if verification passes"
)
```

---

## Detailed Workflow

### Parent Uploads Receipt

1. **Parent visits invoice page** (`/portal/parent/invoices/<id>/`)
2. **Clicks "Upload Payment Receipt"**
3. **Uploads receipt file** (PDF/image)
4. **Enters payment details**:
   - Payment method (CASH, BANK)
   - Transaction reference (optional)
   - Amount paid (optional - can be extracted)
   - Notes (optional)
5. **Submits form**
6. **System creates `PaymentProofUpload`** (status: PENDING)

### Automated Verification (Background Task)

1. **Celery task runs** (or triggered immediately)
2. **Extracts data from receipt**:
   - Amount (e.g., "50,000 XAF" → 50000)
   - Transaction reference (e.g., "TXN123456")
   - Date (e.g., "2026-02-03")
3. **Verifies against invoice**:
   - Amount matches invoice balance (within tolerance)?
   - Reference matches invoice payment_code?
   - Date is recent (within 30 days)?
4. **Calculates confidence score** (0.0-1.0)

### Auto-Apply or Flag for Review

**If confidence >= threshold AND no discrepancies**:
1. Create `Payment` record:
   - `invoice` = invoice
   - `amount` = extracted amount
   - `method` = CASH/BANK
   - `receipt_file` = uploaded file
   - `reference` = transaction reference
   - `status` = "completed"
   - `created_by` = parent user
2. Call `apply_payment(payment)` → Updates invoice status
3. Update `PaymentProofUpload`:
   - `status` = VERIFIED
   - `payment` = created payment
   - `verified_at` = now
4. Send notification to parent: "Payment verified and applied"

**If confidence < threshold OR discrepancies**:
1. Update `PaymentProofUpload`:
   - `status` = DISCREPANCY
   - `verification_notes` = discrepancy details
2. Send notification to admin: "Receipt verification needs review"
3. Send notification to parent: "Receipt received, under review"

### Admin Review (If Needed)

1. **Admin views pending receipts** (`/admin/finance/paymentproofupload/`)
2. **Reviews receipt and verification data**
3. **Options**:
   - **Approve**: Create Payment → Apply
   - **Reject**: Mark as REJECTED, notify parent
   - **Request More Info**: Send message to parent

---

## Integration with Payment Gateways

### Current Integration Points

1. **MTN MoMo / Orange Money**:
   - Webhook receives payment confirmation
   - Creates Payment automatically
   - No receipt upload needed (gateway confirms)

2. **Bank Transfer**:
   - **Current**: Manual entry by admin
   - **New**: Parent uploads receipt → Auto-verify → Auto-apply

3. **Cash Payment**:
   - **Current**: Admin records at school office
   - **New**: Parent uploads receipt → Auto-verify → Auto-apply
   - **Alternative**: Admin can still record manually

### Unified Payment Flow

```
Payment Method → Processing → Application
─────────────────────────────────────────────
MTN MoMo      → Webhook     → Auto-apply ✅
Orange Money  → Webhook     → Auto-apply ✅
Bank Transfer → Receipt Upload → Verify → Auto-apply ✅ (NEW)
Cash          → Receipt Upload → Verify → Auto-apply ✅ (NEW)
              → Manual Entry → Admin → Apply ✅ (Still available)
```

---

## Technical Implementation

### 1. Receipt Verification Service

**Pattern Matching (Free, No API Required)**:
```python
import re
from decimal import Decimal

def extract_amount_from_text(text: str) -> Decimal | None:
    """Extract amount from receipt text using patterns."""
    # Look for currency + number patterns
    patterns = [
        r'(\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?)\s*(?:XAF|FCFA|CFA)',
        r'(?:XAF|FCFA|CFA)\s*(\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?)',
        r'Amount[:\s]+(\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?)',
        r'Total[:\s]+(\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?)',
    ]
    # ... extract and return Decimal
```

**OCR Integration (Optional)**:
```python
# Option A: Tesseract (free)
try:
    import pytesseract
    from PIL import Image
    text = pytesseract.image_to_string(Image.open(receipt_file))
    amount = extract_amount_from_text(text)
except ImportError:
    # Fallback to pattern matching
    pass

# Option B: Cloud OCR (paid)
# Google Vision API, AWS Textract, etc.
```

### 2. Payment Matching Logic

```python
def match_receipt_to_invoice(receipt_data: dict, invoice: Invoice) -> dict:
    """Match receipt to invoice and verify."""
    amount_match = abs(receipt_data["amount"] - invoice.balance_amount) < Decimal("1.00")
    reference_match = (
        receipt_data.get("reference") == invoice.payment_code or
        receipt_data.get("reference") == invoice.reference
    )
    confidence = 0.0
    if amount_match:
        confidence += 0.7
    if reference_match:
        confidence += 0.3
    
    return {
        "matches": confidence >= 0.7,
        "amount_match": amount_match,
        "reference_match": reference_match,
        "confidence": confidence,
        "discrepancies": [] if confidence >= 0.7 else ["Amount mismatch" if not amount_match else "Reference mismatch"]
    }
```

### 3. Automated Payment Creation

```python
@transaction.atomic
def create_payment_from_receipt(
    proof_upload: PaymentProofUpload,
    verification_data: dict
) -> Payment:
    """Create and apply payment from verified receipt."""
    invoice = proof_upload.invoice
    
    # Create payment
    payment = Payment.objects.create(
        invoice=invoice,
        amount=verification_data["amount"],
        method=proof_upload.payment_method,
        receipt_file=proof_upload.receipt_file,
        reference=verification_data.get("reference", ""),
        transaction_reference=verification_data.get("reference", ""),
        status=Payment.STATUS_CHOICES[2][0],  # "completed"
        created_by=proof_upload.uploaded_by,
        paid_at=timezone.now(),
    )
    
    # Apply payment (updates invoice status)
    apply_payment(payment)
    
    # Update proof upload
    proof_upload.payment = payment
    proof_upload.status = PaymentProofUpload.Status.VERIFIED
    proof_upload.verified_at = timezone.now()
    proof_upload.save()
    
    return payment
```

---

## SiteSettings Configuration

```python
# Receipt Verification & Automation
finance_receipt_upload_enabled = BooleanField(
    default=True,
    help_text="Enable receipt upload in parent portal"
)
finance_receipt_auto_verify_enabled = BooleanField(
    default=True,
    help_text="Automatically verify uploaded receipts"
)
finance_receipt_verification_method = CharField(
    choices=[
        ("pattern", "Pattern Matching (Free)"),
        ("ocr_tesseract", "Tesseract OCR (Free, requires installation)"),
        ("ocr_cloud_google", "Google Vision API (Paid)"),
        ("ocr_cloud_aws", "AWS Textract (Paid)"),
    ],
    default="pattern"
)
finance_receipt_auto_apply_threshold = FloatField(
    default=0.9,
    help_text="Confidence threshold (0.0-1.0) for auto-applying payments. Lower = more automatic, Higher = more manual review."
)
finance_receipt_auto_apply_enabled = BooleanField(
    default=True,
    help_text="Automatically apply payments when verification confidence exceeds threshold"
)
finance_receipt_require_admin_approval = BooleanField(
    default=False,
    help_text="Require admin approval even if verification passes (for extra security)"
)
finance_receipt_amount_tolerance = DecimalField(
    max_digits=10,
    decimal_places=2,
    default=Decimal("1.00"),
    help_text="Tolerance for amount matching (e.g., 1.00 XAF difference allowed)"
)
```

---

## Admin UI

### PaymentProofUpload Admin
- **List View**: Show all uploads with status, invoice, amount, confidence
- **Filters**: Status, payment method, date range
- **Actions**:
  - "Approve Selected" → Create Payment → Apply
  - "Reject Selected" → Mark rejected, notify parent
  - "Re-verify Selected" → Re-run verification

### Invoice Detail Page
- Show uploaded receipts with status
- Show verification results
- Link to created Payment (if verified)

---

## Parent Portal UI

### Invoice Detail Page Updates
- **"Upload Payment Receipt" button** (if invoice not paid)
- **Upload form**:
  - File upload (drag & drop)
  - Payment method dropdown (CASH, BANK)
  - Transaction reference (optional)
  - Amount (optional - auto-filled if extracted)
  - Notes (optional)
- **Receipt status display**:
  - "Pending Verification" (with spinner)
  - "Verified - Payment Applied" (with success icon)
  - "Under Review" (with info icon)
  - "Rejected" (with error icon + reason)

---

## Notification Integration

### Parent Notifications
- **Receipt Uploaded**: "Your receipt has been received and is being verified"
- **Payment Verified**: "Your payment of {amount} has been verified and applied to invoice {reference}"
- **Needs Review**: "Your receipt is under review. We'll notify you once verified."
- **Rejected**: "Your receipt was rejected. Reason: {reason}. Please contact finance."

### Admin Notifications
- **Receipt Needs Review**: "New receipt upload requires review: Invoice {reference}, Amount {amount}"
- **Discrepancy Found**: "Receipt verification found discrepancy: {details}"

---

## Benefits

1. **Reduces Admin Work**: No manual payment entry for cash/bank payments
2. **Faster Processing**: Automatic verification and application
3. **Better Accuracy**: OCR/pattern matching reduces human error
4. **Parent Convenience**: Upload receipts anytime, anywhere
5. **Audit Trail**: Complete record of receipt uploads and verifications
6. **Scalability**: Handles high volume of receipts automatically

---

## Implementation Priority

### Phase 1 (High Priority - Quick Win)
1. ✅ Parent portal receipt upload interface
2. ✅ PaymentProofUpload model
3. ✅ Basic pattern matching for amount extraction
4. ✅ Manual admin review workflow

### Phase 2 (Medium Priority - Automation)
5. ✅ Automated verification task
6. ✅ Auto-apply when confidence high
7. ✅ Notification integration

### Phase 3 (Low Priority - Enhancement)
8. ⏳ OCR integration (Tesseract or cloud)
9. ⏳ Advanced pattern matching
10. ⏳ Machine learning for receipt format recognition

---

## Testing Strategy

### Unit Tests
- Receipt data extraction (pattern matching)
- Amount/reference matching logic
- Payment creation from receipt
- Confidence calculation

### Integration Tests
- Full workflow: Upload → Verify → Apply
- Discrepancy handling
- Admin approval workflow

### Manual Testing
- Upload various receipt formats
- Test with different payment methods
- Verify auto-application works
- Test admin review workflow

---

## Next Steps

1. **Create PaymentProofUpload model**
2. **Add parent portal upload view**
3. **Create receipt verification service**
4. **Add automated processing task**
5. **Update admin UI**
6. **Add notifications**

---

**Status**: 📋 **PLAN READY FOR IMPLEMENTATION**
