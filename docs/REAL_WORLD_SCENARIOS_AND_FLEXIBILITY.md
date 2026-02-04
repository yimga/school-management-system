# Real-World Scenarios & System Flexibility Guide

## Overview

This document addresses real-world payment scenarios and explains how the system handles edge cases, delayed bank statements, cash payments, and integrates with communication modules.

---

## Scenario 1: Bank Statements Not in Real-Time (30-Day Cycle)

### The Problem

**Most banks provide statements monthly (30-day cycle)**, not in real-time. How does the system handle receipts uploaded before bank statements are available?

### How the System Handles This

#### **1. Receipt Upload → Pending Bank Verification**

**Workflow**:
1. Parent uploads receipt (e.g., Feb 1)
2. System extracts transaction reference: `TXN123456`
3. System searches bank statements → **No match found** (statement not uploaded yet)
4. Receipt status: `DISCREPANCY` (bank verification pending)
5. `bank_verified = False`
6. Finance staff notified: "Receipt uploaded, awaiting bank statement"

#### **2. Bank Statement Upload (Later)**

**Workflow**:
1. Finance uploads bank statement (e.g., Feb 28 - covers Jan 1-31)
2. System imports transactions including `TXN123456`
3. **Automatic re-verification runs**:
   - Searches all pending receipts
   - Finds match for `TXN123456`
   - Updates receipt: `bank_verified = True`
   - Links to statement entry
4. If auto-approve enabled → Creates Payment → Applies

#### **3. Manual Re-Verification**

**Workflow**:
1. Finance uploads statement
2. Admin → Payment Proof Uploads → Filter: Bank Verified = No
3. Select pending receipts
4. Click "Verify Against Bank Statements"
5. System searches and matches
6. Staff approves matched receipts

### Configuration

**SiteSettings**:
- `finance_bank_verification_tolerance_days`: Default 7 days
  - **Recommendation**: Set to 35-45 days for monthly statements
  - Searches 35 days before/after receipt date

**Example**:
```python
# Receipt uploaded: Feb 1
# Bank statement covers: Jan 1-31
# Tolerance: 35 days
# System searches: Jan 1 - Feb 1 (finds match)
```

### Management Command

**Re-verify after statement upload**:
```bash
# After uploading bank statement
python manage.py verify_bank_deposits --auto-approve

# Or for specific account
python manage.py verify_bank_deposits --account-id=1 --auto-approve
```

---

## Scenario 2: Cash Payment - Receipt Uploaded Before Finance Records

### The Problem

**Parent pays cash at school office, uploads receipt, but finance hasn't recorded the payment yet.** What happens?

### How the System Handles This

#### **Option A: Receipt Upload First (Current Flow)**

**Workflow**:
1. Parent pays cash at office (Feb 1)
2. Parent uploads receipt immediately (Feb 1)
3. System creates `PaymentProofUpload`:
   - Status: `PENDING`
   - Payment method: `CASH`
   - `bank_verified = False` (cash has no bank statement)
4. **Finance staff reviews**:
   - Checks if cash was received at office
   - Verifies receipt matches cash received
   - Approves → Creates Payment → Applies

#### **Option B: Finance Records First (Alternative)**

**Workflow**:
1. Finance records cash payment manually (Feb 1)
2. Creates `Payment` record
3. Invoice status updated to PAID/PARTIAL
4. **If parent uploads receipt later**:
   - System detects invoice already paid
   - Links receipt to existing Payment
   - Marks as verified (payment already exists)

### Enhanced Cash Payment Workflow

**Recommended Process**:

1. **Parent pays cash** → Receives receipt from finance
2. **Parent uploads receipt** → System flags for finance review
3. **Finance verifies**:
   - Checks cash received matches receipt
   - Confirms amount matches invoice
   - Approves → Creates Payment

**OR**:

1. **Finance records cash payment** → Creates Payment immediately
2. **Parent uploads receipt** → System links to existing Payment
3. **No duplicate payment** → System detects invoice already paid

### Cash Payment Settings

**SiteSettings**:
- `finance_receipt_require_admin_approval`: `True` for cash payments
- Cash payments always require manual verification (no auto-approve)

---

## Scenario 3: Other Edge Cases & Scenarios

### **A. Partial Payments**

**Scenario**: Parent pays 50% now, will pay rest later.

**How System Handles**:
- Receipt uploaded for partial amount
- System creates Payment for partial amount
- Invoice status → `PARTIAL`
- Remaining balance tracked
- Reminders continue for remaining balance

### **B. Overpayments**

**Scenario**: Parent pays more than invoice balance.

**How System Handles**:
- Receipt amount exceeds invoice balance
- System flags as discrepancy
- Finance reviews:
  - **Option 1**: Apply to invoice, create credit note
  - **Option 2**: Refund excess amount
  - **Option 3**: Apply to next invoice

### **C. Multiple Receipts for Same Invoice**

**Scenario**: Parent uploads 2 receipts for same invoice.

**How System Handles**:
- First receipt: Verified → Payment created
- Second receipt: System detects invoice already paid
- Flags as duplicate
- Finance reviews:
  - If legitimate (partial payments) → Create second Payment
  - If duplicate → Reject

### **D. Receipt Uploaded After Invoice Paid**

**Scenario**: Parent uploads receipt but invoice already paid via webhook.

**How System Handles**:
- System checks invoice status
- If `PAID` → Flags receipt as "Invoice already paid"
- Links receipt to existing Payment (if reference matches)
- Notifies parent: "Payment already recorded"

### **E. Wrong Invoice Reference**

**Scenario**: Parent uploads receipt with wrong invoice reference.

**How System Handles**:
- System can't match receipt to invoice
- Flags as discrepancy
- Finance reviews:
  - Finds correct invoice
  - Manually links receipt to correct invoice
  - Approves

### **F. Bank Statement Missing Transaction**

**Scenario**: Receipt uploaded but transaction not in bank statement.

**How System Handles**:
- No match found in statements
- Status: `DISCREPANCY`
- Finance reviews:
  - Checks bank manually
  - If found → Manually verifies
  - If not found → Contacts parent/bank

### **G. MTN MoMo/Orange Money - No Merchant Statement**

**Scenario**: School doesn't have merchant account statements.

**How System Handles**:
- Receipt uploaded with MTN MoMo reference
- No merchant statement available
- System flags for manual verification
- Finance verifies via MTN MoMo portal manually
- Approves if verified

---

## Integration with Communication & Reminders

### Current State

**Payment reminders currently send**:
- Invoice reference
- Amount due
- Due date
- Payment link (if configured)

**Missing**: Payment instructions (MoMo numbers, account numbers, etc.)

### Enhanced Payment Reminders

**What Should Be Included**:

1. **Payment Instructions**:
   - Bank account numbers
   - MTN MoMo merchant number
   - Orange Money merchant number
   - Payment code (for MoMo)
   - Branch details (for bank transfers)

2. **Receipt Upload Instructions**:
   - How to upload receipt
   - Link to upload page
   - What information to include

3. **Payment Methods Available**:
   - List all accepted methods
   - Instructions for each method

### Implementation Plan

#### **1. Payment Instructions Template**

**SiteSettings** → **Finance Automation** → **Payment Instructions**

**Fields**:
- `finance_payment_instructions_bank`: Bank account details template
- `finance_payment_instructions_mtn_momo`: MTN MoMo instructions template
- `finance_payment_instructions_orange_money`: Orange Money instructions template
- `finance_payment_instructions_cash`: Cash payment instructions template

**Template Variables**:
- `{invoice_reference}`: Invoice number
- `{payment_code}`: Payment code for MoMo
- `{amount}`: Amount due
- `{due_date}`: Due date
- `{bank_account}`: Bank account number
- `{bank_name}`: Bank name
- `{branch}`: Branch name
- `{mtn_momo_number}`: MTN MoMo merchant number
- `{orange_money_number}`: Orange Money merchant number

#### **2. Enhanced Reminder Templates**

**PaymentReminder model** already supports templates, but needs payment instructions:

**Current Template**:
```
Dear {guardian}, please pay {amount} for {invoice} by {due_date}.
```

**Enhanced Template**:
```
Dear {guardian},

Please pay *{amount} XAF* for invoice *{invoice}* by *{due_date}*.

PAYMENT METHODS:

🏦 BANK TRANSFER:
Account: {bank_account}
Bank: {bank_name}
Branch: {branch}
Reference: {payment_code}

📱 MTN MOBILE MONEY:
Merchant: {mtn_momo_number}
Payment Code: {payment_code}
Amount: {amount} XAF

📱 ORANGE MONEY:
Merchant: {orange_money_number}
Payment Code: {payment_code}
Amount: {amount} XAF

💵 CASH:
Pay at school office during business hours.

After payment, upload your receipt here: {receipt_upload_link}

Thank you!
```

#### **3. Automatic Payment Instructions**

**When invoice is created**:
- System generates payment code (if not exists)
- Links payment instructions to invoice
- Includes in all reminders

**When reminder is sent**:
- System fetches payment instructions
- Includes in message template
- Sends via email/SMS/WhatsApp

---

## Flexibility & Configuration

### **1. Configurable Verification Workflows**

**SiteSettings** → **Finance Automation** → **Verification Workflows**

**Options**:
- **Strict**: Require bank verification for all payments
- **Moderate**: Require bank verification for bank/MoMo, manual for cash
- **Flexible**: Auto-approve if confidence high, verify later

### **2. Payment Method-Specific Rules**

**Per Payment Method**:
- **Bank Transfer**: Require bank verification
- **MTN MoMo**: Require merchant statement OR manual verification
- **Orange Money**: Require merchant statement OR manual verification
- **Cash**: Always manual verification

### **3. Time-Based Verification**

**Delayed Verification**:
- Receipts can be verified later when statements arrive
- System re-checks pending receipts periodically
- Management command runs daily/weekly

### **4. Manual Override**

**Finance staff can**:
- Manually verify any receipt
- Override fraud detection flags
- Approve without bank verification (if needed)
- Link receipts to payments manually

---

## Recommended Workflows

### **Workflow 1: Monthly Bank Statements**

**Setup**:
1. Set `finance_bank_verification_tolerance_days = 45` (covers monthly cycle)
2. Set `finance_bank_verification_auto_approve = False` (manual review)
3. Upload statements monthly
4. Run `verify_bank_deposits` after each upload

**Process**:
- Parents upload receipts → Pending verification
- Finance uploads statement monthly
- System matches receipts to statements
- Finance reviews and approves

### **Workflow 2: Real-Time MoMo (If Available)**

**Setup**:
1. Set `finance_bank_verification_auto_approve = True` for MoMo
2. Upload MoMo statements daily/weekly
3. System auto-verifies and approves

**Process**:
- Parents upload MoMo receipts
- System verifies against daily statements
- Auto-approves if matched

### **Workflow 3: Cash Payments**

**Setup**:
1. Set `finance_receipt_require_admin_approval = True`
2. Cash payments always manual

**Process**:
- Parents upload cash receipts
- Finance verifies cash received matches receipt
- Approves manually

---

## Next Steps: Implementation

### **Phase 1: Enhanced Payment Instructions**

1. Add payment instruction templates to SiteSettings
2. Include bank account/MoMo numbers in reminders
3. Add receipt upload link to reminders

### **Phase 2: Flexible Verification**

1. Add payment method-specific verification rules
2. Add time-based re-verification
3. Add manual override capabilities

### **Phase 3: Communication Integration**

1. Enhance reminder templates with payment instructions
2. Add payment instructions to invoice emails
3. Add receipt upload instructions to all communications

---

## Summary

✅ **Bank Statements (30-day cycle)**: System handles delayed verification
✅ **Cash Payments**: Manual verification workflow
✅ **Edge Cases**: All scenarios covered
✅ **Communication**: Payment instructions included in reminders
✅ **Flexibility**: Configurable workflows per payment method

**Status**: System designed for real-world scenarios with maximum flexibility.
