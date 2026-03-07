# Real-World Scenarios Implementation

## Summary of Enhancements

This document details the enhancements made to handle real-world payment scenarios and improve system flexibility.

---

## ✅ Implemented Features

### 1. **Delayed Bank Statement Verification**

**Problem**: Bank statements arrive monthly (30-day cycle), not real-time.

**Solution**:
- Receipts remain in `PENDING` status until bank verification
- System retries verification when statements are uploaded
- Configurable tolerance days (default: 7, recommended: 35-45 for monthly)
- Management command: `retry_bank_verification_task` for periodic re-checks

**Workflow**:
1. Parent uploads receipt → Status: PENDING (bank_verified=False)
2. Finance uploads statement later → System re-verifies automatically
3. If match found → bank_verified=True → Auto-approve (if enabled)

### 2. **Cash Payment Workflow**

**Problem**: Cash payments need manual verification (no bank statement).

**Solution**:
- Cash receipts skip bank verification automatically
- Always require manual approval (configurable)
- Finance staff verifies cash received matches receipt
- Can link to existing Payment if finance recorded first

**Workflow**:
1. Parent uploads cash receipt → Status: PENDING
2. System skips bank verification (payment_method=CASH)
3. Finance reviews → Verifies cash received → Approves
4. Payment created and applied

### 3. **Enhanced Payment Reminders with Instructions**

**Problem**: Reminders don't include payment instructions (MoMo numbers, account numbers).

**Solution**:
- Payment instructions automatically included in all reminders
- Templates support variables: `{bank_account}`, `{mtn_momo_number}`, `{orange_money_number}`, `{payment_code}`
- Instructions fetched from BankAccount model
- Customizable templates per payment method

**Enhanced Templates**:
- **Email**: Full payment instructions with all methods
- **SMS**: Condensed format
- **WhatsApp**: Formatted with emojis

### 4. **Payment Method-Specific Rules**

**Configuration**:
- **Bank Transfer**: Require bank verification
- **MTN MoMo**: Require merchant statement OR manual verification
- **Orange Money**: Require merchant statement OR manual verification
- **Cash**: Always manual verification (no bank statement)

### 5. **Retry Mechanism for Delayed Verification**

**New Task**: `retry_bank_verification_task`

**Purpose**: Re-verify receipts that failed earlier when new statements arrive.

**Usage**:
```bash
# Retry verification for receipts older than 30 days
python manage.py shell
>>> from apps.finance.tasks import retry_bank_verification_task
>>> retry_bank_verification_task(days_old=30)
```

**Scheduled**: Can be run daily/weekly via Celery Beat to check for new statements.

---

## Edge Cases Handled

### ✅ **Partial Payments**
- System creates Payment for partial amount
- Invoice status → PARTIAL
- Reminders continue for remaining balance

### ✅ **Overpayments**
- Flagged as discrepancy
- Finance can create credit note or refund

### ✅ **Multiple Receipts Same Invoice**
- First receipt verified → Payment created
- Second receipt flagged as duplicate
- Finance can approve if legitimate (partial payments)

### ✅ **Receipt After Invoice Paid**
- System detects invoice already paid
- Links receipt to existing Payment
- Notifies parent

### ✅ **Wrong Invoice Reference**
- Can't match receipt to invoice
- Flagged for manual review
- Finance can manually link to correct invoice

### ✅ **Missing Transaction in Statement**
- No match found
- Status: DISCREPANCY
- Finance reviews manually

### ✅ **No Merchant Statements (MoMo)**
- Flags for manual verification
- Finance verifies via MoMo portal
- Approves if verified

---

## Communication Integration

### **Payment Reminders Include**:

1. **Invoice Details**:
   - Invoice reference
   - Amount due
   - Due date

2. **Payment Instructions**:
   - Bank account number
   - Bank name and branch
   - MTN MoMo merchant number
   - Orange Money merchant number
   - Payment code (for MoMo)

3. **Receipt Upload Link**:
   - Direct link to upload receipt
   - Instructions on what to include

4. **Payment Methods**:
   - All available methods listed
   - Instructions for each method

### **Template Variables Available**:

- `{guardian}`: Parent/guardian name
- `{amount}`: Amount due
- `{invoice}`: Invoice reference
- `{due_date}`: Due date
- `{payment_code}`: Payment code for MoMo
- `{bank_account}`: Bank account number
- `{bank_name}`: Bank name
- `{branch}`: Branch name
- `{mtn_momo_number}`: MTN MoMo merchant number
- `{orange_money_number}`: Orange Money merchant number
- `{receipt_upload_link}`: Link to upload receipt
- `{link}`: Payment link (if configured)

---

## Configuration Recommendations

### **For Monthly Bank Statements**:

```python
# SiteSettings
finance_bank_verification_tolerance_days = 45  # Covers monthly cycle
finance_bank_verification_auto_approve = False  # Manual review recommended
```

### **For Real-Time MoMo (If Available)**:

```python
# SiteSettings
finance_bank_verification_tolerance_days = 7  # Daily/weekly statements
finance_bank_verification_auto_approve = True  # Auto-approve for MoMo
```

### **For Cash Payments**:

```python
# SiteSettings
finance_receipt_require_admin_approval = True  # Always manual
```

---

## Workflow Examples

### **Example 1: Monthly Bank Statement**

**Timeline**:
- Feb 1: Parent uploads bank transfer receipt
- Feb 1-28: Receipt pending (no statement yet)
- Feb 28: Finance uploads January statement
- Feb 28: System re-verifies → Finds match → Approves

**Configuration**:
- Tolerance: 45 days
- Auto-approve: False (manual review)

### **Example 2: Cash Payment**

**Timeline**:
- Feb 1: Parent pays cash at office
- Feb 1: Parent uploads receipt
- Feb 1: System flags for manual review (cash = no bank verification)
- Feb 2: Finance verifies cash received → Approves

**Configuration**:
- Cash: Always manual approval

### **Example 3: MTN MoMo Without Merchant Statement**

**Timeline**:
- Feb 1: Parent uploads MTN MoMo receipt
- Feb 1: System searches merchant statements → No match
- Feb 1: Status: DISCREPANCY (manual verification)
- Feb 2: Finance verifies via MTN portal → Approves

**Configuration**:
- MoMo: Manual verification if no merchant statement

---

## Files Modified

### **Enhanced**:
- `apps/finance/tasks.py`:
  - Added `_get_payment_instructions()` function
  - Enhanced reminder context with payment instructions
  - Added `retry_bank_verification_task` for delayed verification
  - Skip bank verification for cash payments

- `apps/finance/models.py`:
  - Enhanced PaymentReminder templates with payment instructions
  - Added `verification_retry_count` and `last_verification_attempt` fields
  - Added payment instruction template fields to SiteSettings

- `apps/siteconfig/models.py`:
  - Added payment instruction template fields
  - Added receipt upload instructions field

- `apps/siteconfig/admin.py`:
  - Added "Payment Instructions" fieldset

- `apps/siteconfig/forms.py`:
  - Added payment instruction fields to field order

---

## Next Steps

1. **Set Up Bank Accounts**:
   - Admin → Finance → Bank Accounts
   - Add bank accounts, MTN MoMo, Orange Money accounts
   - These will automatically appear in payment reminders

2. **Customize Payment Instructions**:
   - Site Settings → Finance Automation → Payment Instructions
   - Customize templates for each payment method
   - Add school-specific instructions

3. **Schedule Retry Task** (Optional):
   - Add to Celery Beat schedule
   - Runs daily/weekly to re-verify pending receipts

4. **Test Reminders**:
   - Create test invoice
   - Send reminder
   - Verify payment instructions included

---

**Status**: ✅ **IMPLEMENTATION COMPLETE** - System handles all real-world scenarios with maximum flexibility.
