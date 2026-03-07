# Bank Deposit Verification & Additional Improvements

## Overview

This document describes bank deposit verification and additional fraud detection improvements, specifically designed for Cameroon's payment ecosystem (MTN MoMo, Orange Money, bank transfers).

---

## Bank Deposit Verification

### The Problem

Parents upload receipts, but **how do we know the money actually arrived in the bank account?**

**Solution**: Verify receipts against actual bank statements.

### How It Works

1. **Staff uploads bank statements** (CSV, PDF, Excel)
2. **System imports transactions** from statements
3. **When parent uploads receipt**, system automatically:
   - Searches bank statements for matching transaction
   - Matches by transaction reference (most reliable)
   - Or matches by amount + date (within tolerance)
4. **If match found** → Mark as verified
5. **If no match** → Flag for manual review

### Supported Payment Methods (Cameroon)

#### 1. **Bank Transfers**
- Verify against bank account statements
- Match by transaction reference
- Match by amount + date

#### 2. **MTN Mobile Money**
- Verify against MTN MoMo merchant account statements
- Match by transaction reference (format: MMXXXXXXXXX or numeric)
- Cameroon-specific format handling

#### 3. **Orange Money**
- Verify against Orange Money merchant account statements
- Match by transaction reference
- Cameroon-specific format handling

#### 4. **Cash Payments**
- Manual verification (no bank statement)
- Staff confirms cash received at office

---

## Implementation

### 1. Bank Account Management

**Admin → Finance → Bank Accounts**

Staff can add school bank accounts:
- **Bank Account**: Traditional bank (AFC, UBA, Ecobank, etc.)
- **MTN MoMo**: MTN Mobile Money merchant account
- **Orange Money**: Orange Money merchant account

**Fields**:
- Account name/nickname
- Account number
- Bank name (for bank accounts)
- Branch
- Currency (XAF for Cameroon)
- Active status

### 2. Bank Statement Upload

**Admin → Finance → Bank Statements → Upload Statement**

Staff uploads bank statements:
- **File formats**: CSV, PDF, Excel
- **Period**: Start date, end date
- **Account**: Select bank account
- **Auto-import**: System extracts transactions

**Import Process**:
1. Upload statement file
2. System parses transactions
3. Creates `BankStatementEntry` records
4. Shows import summary (entries imported, errors)

### 3. Automatic Verification

**When parent uploads receipt**:

1. **Receipt uploaded** → `PaymentProofUpload` created
2. **Background task runs** → Searches bank statements
3. **If match found**:
   - Updates `bank_verified = True`
   - Links to matched `BankStatementEntry`
   - Records verification method
4. **If no match**:
   - Keeps `bank_verified = False`
   - Flags for manual review

**Verification Methods**:
- **Transaction Reference** (confidence: 95%)
  - Exact match of transaction reference
  - Most reliable method
- **Amount + Date** (confidence: 70-90%)
  - Matches amount within tolerance (default: 1.00 XAF)
  - Matches date within tolerance (default: 7 days)
  - Less reliable but useful if reference missing

### 4. Manual Verification

**Admin → Payment Proof Uploads → Filter: Bank Verified = No**

Staff can manually verify:
1. View receipt upload
2. Check bank statements manually
3. Click "Verify Bank Deposit"
4. Select matching bank statement entry
5. Save → Marks as verified

---

## Additional Fraud Detection Improvements

### 1. **IP Address Tracking** 🌐

**What it detects**:
- Multiple users uploading from same IP
- VPN/proxy usage
- Suspicious location patterns

**Implementation**:
- Captures IP address on receipt upload
- Checks if same IP used by multiple users
- Flags if 3+ different users from same IP in 24 hours
- Risk score: +15

### 2. **Device Fingerprinting** 📱

**What it detects**:
- Same device used by multiple accounts
- Device manipulation

**Implementation**:
- Captures user agent/browser info
- Creates device fingerprint hash
- Tracks devices across uploads
- Flags suspicious device patterns

### 3. **Upload Velocity** ⚡

**What it detects**:
- Rapid uploads (potential automation)
- Unusual upload patterns

**Implementation**:
- Tracks upload frequency per user
- Flags if 3+ uploads within 1 hour
- Risk score: +20

### 4. **Amount Pattern Analysis** 💰

**What it detects**:
- Round numbers (suspicious)
- Amounts matching previous fraudulent receipts
- Unusual amount patterns

**Implementation**:
- Analyzes amount patterns
- Flags round numbers (e.g., 100,000 exactly)
- Compares with historical fraudulent amounts
- Risk score: +10

### 5. **Reference Pattern Analysis** 🔍

**What it detects**:
- Fake transaction references
- References that don't match payment method format

**Implementation**:
- Validates reference format per payment method
- MTN MoMo: Should be numeric or MMXXXXXXXXX
- Orange Money: Should be numeric
- Bank: Should match bank's format
- Risk score: +15

---

## Staff Intervention Tools

### 1. **Manual Bank Verification**

**Admin → Payment Proof Uploads → [Select Receipt] → Verify Bank Deposit**

**Workflow**:
1. View receipt upload details
2. Click "Verify Bank Deposit"
3. Search bank statements:
   - By transaction reference
   - By amount + date range
   - By description/keywords
4. Select matching statement entry
5. Click "Verify" → Marks as verified

### 2. **Bulk Verification**

**Admin → Payment Proof Uploads → Actions → Verify Selected Against Bank Statements**

**Workflow**:
1. Select multiple receipt uploads
2. Click "Verify Against Bank Statements"
3. System searches all selected receipts
4. Shows verification results
5. Staff can approve/reject individually

### 3. **Bank Reconciliation Dashboard**

**Admin → Finance → Bank Reconciliation**

**Shows**:
- **Unmatched Receipts**: Receipts without bank verification
- **Unmatched Deposits**: Bank deposits without matching receipts
- **Matched**: Successfully verified receipts
- **Discrepancies**: Amount/date mismatches

**Actions**:
- Match receipts to deposits manually
- Flag discrepancies for review
- Export reconciliation report

### 4. **Manual Payment Creation**

**Admin → Payment Proof Uploads → [Select Receipt] → Create Payment**

**Workflow**:
1. Staff reviews receipt
2. Verifies bank deposit (or confirms cash received)
3. Clicks "Create Payment"
4. System creates Payment record
5. Payment applied to invoice

---

## Management Commands

### Verify Bank Deposits

**Command**: `python manage.py verify_bank_deposits`

**Options**:
- `--auto-approve`: Automatically approve verified deposits
- `--account-id=1`: Verify only for specific bank account
- `--days=7`: Days to search before/after receipt date

**Usage**:
```bash
# Verify all pending receipts
python manage.py verify_bank_deposits

# Auto-approve verified deposits
python manage.py verify_bank_deposits --auto-approve

# Verify only MTN MoMo account
python manage.py verify_bank_deposits --account-id=2 --auto-approve
```

---

## Cameroon-Specific Features

### 1. **MTN MoMo Verification**

**Format Handling**:
- Supports references: `MM123456789` or `123456789`
- Normalizes references (removes MM prefix)
- Matches against MTN MoMo merchant statements

**Bank Account Setup**:
- Account Type: MTN Mobile Money
- Account Number: MTN MoMo merchant number
- System automatically handles MTN-specific formats

### 2. **Orange Money Verification**

**Format Handling**:
- Supports numeric references
- Matches against Orange Money merchant statements

**Bank Account Setup**:
- Account Type: Orange Money
- Account Number: Orange Money merchant number
- System automatically handles Orange-specific formats

### 3. **Cameroon Bank Formats**

**Supported Banks**:
- AFC (Afriland First Bank)
- UBA (United Bank for Africa)
- Ecobank
- Standard Chartered
- BICEC
- Others

**Account Number Formats**:
- 10-15 digit account numbers
- System validates format per bank

---

## Workflow Examples

### Example 1: Bank Transfer Verification

1. **Parent uploads receipt**:
   - Payment method: BANK
   - Transaction reference: TXN20260203123456
   - Amount: 50,000 XAF
   - Date: 2026-02-03

2. **System searches bank statements**:
   - Looks for TXN20260203123456 in bank account statements
   - Searches within 7 days of receipt date

3. **Match found**:
   - Bank statement entry: TXN20260203123456, 50,000 XAF, 2026-02-03
   - **Verified** → `bank_verified = True`
   - Links to statement entry

4. **If auto-approve enabled**:
   - Creates Payment record
   - Applies to invoice

### Example 2: MTN MoMo Verification

1. **Parent uploads receipt**:
   - Payment method: MTN_MOMO
   - Transaction reference: MM6789012345
   - Amount: 25,000 XAF

2. **System searches MTN MoMo statements**:
   - Normalizes reference: `6789012345`
   - Searches MTN MoMo merchant account statements

3. **Match found**:
   - MTN statement entry: 6789012345, 25,000 XAF
   - **Verified** → `bank_verified = True`

### Example 3: No Match Found

1. **Parent uploads receipt**:
   - Transaction reference: TXN999999999
   - Amount: 30,000 XAF

2. **System searches bank statements**:
   - No match found for TXN999999999
   - No match by amount + date

3. **Flagged for review**:
   - `bank_verified = False`
   - Status: DISCREPANCY
   - Finance staff notified

4. **Staff reviews**:
   - Checks bank statements manually
   - Finds transaction with different reference
   - Manually verifies and links

---

## Configuration

### SiteSettings

**New Fields**:
- `finance_bank_verification_enabled`: Enable bank verification
- `finance_bank_verification_auto_approve`: Auto-approve verified deposits
- `finance_bank_verification_tolerance_days`: Days to search (default: 7)
- `finance_bank_verification_amount_tolerance`: Amount tolerance (default: 1.00 XAF)

### Bank Account Setup

1. **Add Bank Account**:
   - Admin → Finance → Bank Accounts → Add
   - Select account type (Bank/MTN MoMo/Orange Money)
   - Enter account number
   - Save

2. **Upload Bank Statement**:
   - Admin → Finance → Bank Statements → Upload
   - Select bank account
   - Upload statement file
   - Set period dates
   - Import

---

## Benefits

✅ **Prevents Fraud**: Verifies money actually arrived before approving
✅ **Automated**: Reduces manual verification work
✅ **Cameroon-Specific**: Supports MTN MoMo, Orange Money, banks
✅ **Audit Trail**: Complete record of verifications
✅ **Reconciliation**: Easy to see unmatched receipts/deposits
✅ **Staff Tools**: Manual verification and bulk operations

---

## Files Created/Modified

### Created:
- `apps/finance/bank_verification.py` - Bank deposit verification service
- `apps/finance/management/commands/verify_bank_deposits.py` - Management command
- `docs/BANK_DEPOSIT_VERIFICATION_AND_IMPROVEMENTS.md` - This document

### Modified:
- `apps/finance/models.py` - Added BankAccount, BankStatementEntry, BankStatementUpload models
- `apps/finance/models.py` - Added bank verification fields to PaymentProofUpload
- `apps/finance/fraud_detection.py` - Added IP address analysis
- `apps/finance/views.py` - Capture IP address and user agent on upload

---

**Status**: ✅ **IMPLEMENTATION COMPLETE** - Bank deposit verification and additional fraud detection ready for use.
