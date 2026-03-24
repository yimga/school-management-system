# Fraud Prevention & Payment Reconciliation Guide

## Overview

This document explains how the system prevents fraud from falsified receipts and how finance staff can track who owes vs who doesn't.

---

## Fraud Detection Mechanisms

### 1. **Date Validation** 🗓️

**Problem**: Users upload old receipts with edited dates to make them look recent.

**Detection**:
- Extracts date from receipt (OCR/pattern matching)
- Compares receipt date with upload date
- Flags if receipt is:
  - **Older than 90 days** → Risk score +30
  - **In the future** (beyond 1 day tolerance) → Risk score +50
  - **30-90 days old** → Risk score +10 (low risk, but flagged for review)

**Example**:
```
Receipt date: 2025-11-01 (3 months ago)
Upload date: 2026-02-02
Result: ⚠️ FLAGGED - Receipt is 93 days old
```

### 2. **Duplicate Detection** 🔄

**Problem**: Users reuse same receipt for multiple invoices.

**Detection**:
- **File Hash**: Calculates SHA-256 hash of receipt file
- **Transaction Reference**: Checks if same transaction reference was used before
- Flags if:
  - Same file uploaded for different invoice → Risk score +50
  - Same transaction reference used multiple times → Risk score +40

**Example**:
```
Upload 1: Invoice #123, File hash: abc123... → ✅ Approved
Upload 2: Invoice #456, File hash: abc123... → ⚠️ FLAGGED - Duplicate file
```

### 3. **File Metadata Analysis** 📄

**Problem**: Users edit receipts (crop, modify dates, etc.).

**Detection**:
- Analyzes EXIF data (for images)
- Checks file size (suspicious if < 5KB - might be edited)
- Checks image dimensions (suspicious if very small)
- Flags anomalies → Risk score +5 to +10

### 4. **Upload Pattern Analysis** 📊

**Problem**: Users upload multiple receipts rapidly or repeatedly.

**Detection**:
- Tracks upload frequency per user
- Flags if:
  - **3+ uploads within 24 hours** → Risk score +20
  - **Multiple receipts for same invoice** → Risk score +15

### 5. **Amount Validation** 💰

**Problem**: Users upload receipts with incorrect amounts.

**Detection**:
- Compares receipt amount with invoice balance
- Flags if:
  - Amount exceeds invoice balance by >10% → Risk score +25
  - Amount is <50% of invoice balance → Risk score +20

---

## Fraud Risk Scoring

**Risk Score Range**: 0-100

| Score | Recommendation | Action |
|-------|---------------|--------|
| 0-39 | ✅ Auto-approve | System automatically applies payment |
| 40-69 | ⚠️ Review | Requires admin review before approval |
| 70-100 | 🚨 Reject | High fraud risk - manual review required |

**Risk Score Calculation**:
- Duplicate file: +50
- Duplicate reference: +40
- Future date: +50
- Old receipt (>90 days): +30
- Amount exceeds balance: +25
- Amount too low: +20
- High upload frequency: +20
- Multiple receipts same invoice: +15
- Suspicious file size: +10
- Old receipt (30-90 days): +10
- Suspicious image size: +5

---

## Finance Staff Notifications

### When Suspicious Receipts Are Detected

Finance staff receive **immediate email notifications** when:

1. **Receipt uploaded with fraud flags** (during upload)
2. **High fraud risk detected** (risk score ≥70)
3. **Duplicate detected** (same file/reference)
4. **Date anomalies** (old/future dates)

**Notification includes**:
- Invoice number and student name
- Uploader information
- Fraud risk score and flags
- Direct link to review receipt
- Recommendation (review/reject)

**Who gets notified**:
- Users in "Finance", "Bursar", or "Accountant" groups
- If no groups exist, all staff users

---

## Admin Dashboard - Suspicious Receipts

### Viewing Suspicious Receipts

1. **Admin → Payment Proof Uploads**
2. **Filter by**: "Is Suspicious" = Yes
3. **Sort by**: Fraud Risk Score (highest first)

**Display shows**:
- ⚠️ Red badge for suspicious receipts
- Fraud risk score (0-100)
- Fraud flags (list of detected issues)
- Status (Pending/Discrepancy/Rejected)

### Reviewing Suspicious Receipts

1. Click on suspicious receipt
2. Review **Fraud Detection** section:
   - Fraud risk score
   - Fraud flags (what was detected)
   - File hash (for duplicate checking)
   - Receipt date vs upload date
3. Review **Verification** section:
   - Extracted data (amount, reference, date)
   - Verification confidence
   - Discrepancies
4. **Actions**:
   - **Approve**: If legitimate, create payment
   - **Reject**: If fraudulent, mark as rejected
   - **Request More Info**: Contact parent for clarification

---

## Payment Reconciliation - Who Owes vs Who Doesn't

### Reconciliation Dashboard

**Access**: Finance Dashboard → Payments → Reconciliation

**Shows**:
1. **Outstanding Invoices**:
   - Student name
   - Invoice number
   - Amount due
   - Due date
   - Status (Issued/Partial/Overdue)

2. **Payment Status**:
   - ✅ Paid (fully paid invoices)
   - ⚠️ Partial (partially paid)
   - ❌ Unpaid (no payments)
   - 🚨 Overdue (past due date)

3. **Receipt Uploads Status**:
   - Pending verification
   - Under review (suspicious)
   - Verified and applied
   - Rejected

### Reconciliation Reports

**Generate Report**: Finance Dashboard → Reports → Payment Reconciliation

**Report includes**:
- **By Student**:
  - Total invoices
  - Total paid
  - Outstanding balance
  - Receipt uploads (pending/verified/rejected)

- **By Invoice**:
  - Invoice details
  - Payments received (with method)
  - Receipt uploads (with status)
  - Balance remaining

- **Suspicious Activity**:
  - Receipts flagged for review
  - Duplicate receipts detected
  - Date anomalies
  - Amount mismatches

### Daily Reconciliation Checklist

1. **Check Suspicious Receipts**:
   - Admin → Payment Proof Uploads → Filter: Is Suspicious = Yes
   - Review all flagged receipts
   - Approve legitimate payments
   - Reject fraudulent receipts

2. **Verify Payments**:
   - Check all auto-applied payments from receipts
   - Verify amounts match invoices
   - Confirm transaction references are unique

3. **Review Outstanding Balances**:
   - Finance Dashboard → Outstanding Invoices
   - Identify students with overdue payments
   - Check if receipts were uploaded but not verified

4. **Audit Trail**:
   - Review PaymentAuditLog for all payment activities
   - Check PaymentProofUpload history for patterns
   - Identify repeat offenders (users with multiple suspicious receipts)

---

## Preventing Fraud - Best Practices

### For Finance Staff

1. **Always Review Suspicious Receipts**:
   - Don't auto-approve if risk score ≥40
   - Verify receipt dates match payment dates
   - Check transaction references are unique

2. **Verify Bank/Cash Payments**:
   - Cross-reference with bank statements
   - Verify transaction references with bank records
   - Confirm amounts match bank deposits

3. **Monitor Patterns**:
   - Watch for users with multiple suspicious receipts
   - Flag users with high fraud risk scores
   - Review duplicate file/reference alerts

4. **Document Rejections**:
   - Always add notes when rejecting receipts
   - Explain why receipt was rejected
   - Notify parent with reason

### For Configuration Control Center

1. **Set Appropriate Thresholds**:
   - `finance_receipt_auto_apply_threshold`: 0.9 (90% confidence)
   - `finance_receipt_amount_tolerance`: 1.00 XAF
   - `MAX_RECEIPT_AGE_DAYS`: 90 days

2. **Enable Admin Approval**:
   - Set `finance_receipt_require_admin_approval = True` for extra security
   - All receipts require manual review

3. **Monitor Fraud Scores**:
   - Review fraud risk scores regularly
   - Adjust thresholds based on patterns
   - Block users with repeated fraud attempts

---

## Example Scenarios

### Scenario 1: Old Receipt with Edited Date

**What happens**:
1. Parent uploads receipt dated 3 months ago
2. System extracts date: 2025-11-01
3. Upload date: 2026-02-02
4. System calculates: 93 days old
5. **Fraud detection**: Flags "old_receipt" → Risk score +30
6. **Status**: Discrepancy (requires review)
7. **Notification**: Finance staff notified immediately

**Finance action**:
- Review receipt date
- Verify if payment was actually made on that date
- Check bank records if needed
- Approve if legitimate, reject if fraudulent

### Scenario 2: Duplicate Receipt

**What happens**:
1. Parent uploads receipt for Invoice #123 → ✅ Approved
2. Parent uploads same receipt for Invoice #456
3. System calculates file hash: abc123...
4. **Fraud detection**: Finds duplicate hash → Risk score +50
5. **Status**: Discrepancy (requires review)
6. **Notification**: Finance staff notified immediately

**Finance action**:
- Check if receipt was already used
- Verify which invoice it belongs to
- Reject duplicate upload
- Notify parent that receipt was already applied

### Scenario 3: Future-Dated Receipt

**What happens**:
1. Parent uploads receipt dated 2026-03-15
2. Upload date: 2026-02-02
3. **Fraud detection**: Flags "future_date" → Risk score +50
4. **Status**: Discrepancy (requires review)
5. **Notification**: Finance staff notified immediately

**Finance action**:
- Reject receipt (future dates are invalid)
- Contact parent for correct receipt
- Explain that receipt date cannot be in future

---

## Reconciliation Reports

### Who Owes vs Who Doesn't

**Access**: Finance Dashboard → Reports → Payment Reconciliation

**Report shows**:

1. **Students with Outstanding Balances**:
   ```
   Student Name | Total Due | Paid | Outstanding | Status
   ──────────────────────────────────────────────────────
   John Doe     | 100,000  | 50,000 | 50,000    | Partial
   Jane Smith   | 75,000   | 0      | 75,000    | Unpaid
   ```

2. **Receipt Upload Status**:
   ```
   Invoice | Student | Amount | Receipt Status | Fraud Risk
   ────────────────────────────────────────────────────────
   #123     | John    | 50,000 | Verified ✅    | 0
   #456     | Jane    | 75,000 | Suspicious ⚠️  | 45
   ```

3. **Suspicious Activity Summary**:
   ```
   Total Suspicious Receipts: 5
   High Risk (≥70): 2
   Medium Risk (40-69): 3
   Duplicate Files: 1
   Old Receipts: 2
   ```

---

## Summary

✅ **Fraud Prevention**:
- Date validation (old/future dates)
- Duplicate detection (file hash, transaction reference)
- File metadata analysis
- Upload pattern analysis
- Amount validation

✅ **Notifications**:
- Immediate alerts to finance staff
- Email notifications for suspicious receipts
- Dashboard highlights suspicious items

✅ **Reconciliation**:
- Clear view of who owes vs who doesn't
- Payment status tracking
- Receipt upload status
- Suspicious activity reports

✅ **Admin Tools**:
- Fraud risk scoring (0-100)
- Fraud flags (what was detected)
- Review/approve/reject actions
- Audit trail for all actions

---

**Status**: ✅ **FRAUD PREVENTION IMPLEMENTED** - System automatically detects and flags suspicious receipts, notifies finance staff, and provides reconciliation tools.
