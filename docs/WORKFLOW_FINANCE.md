# Finance Workflows
## Complete Guide to Fees, Payments, and Financial Management

**Target Audience:** Bursars, Finance Staff, Administrators  
**Difficulty:** Intermediate  
**Estimated Time:** 15-30 minutes per invoice batch

---

## Overview

This guide covers creating invoices, processing payments, mobile money integration, and financial reporting.

---

## Invoice Creation

### Single Invoice

**Steps:**
1. Navigate to `/admin/finance/invoice/` or Finance Dashboard
2. Click "Add Invoice"
3. **Fill in:**
   - **Student:** Select student
   - **Invoice Type:** Accounts Receivable
   - **Items:** Add fee items
   - **Amount:** Total amount
   - **Due Date:** Payment deadline
   - **Notes:** Optional
4. Click "Save"
5. Invoice status: "ISSUED"

---

### Bulk Invoice Creation

**When to Use:**
- Start of term fees
- Multiple students
- Same fee structure

**Steps:**
1. Navigate to Finance Dashboard
2. Click "Bulk Create Invoices"
3. **Select:**
   - Academic Year
   - Term (if applicable)
   - Classroom(s) or All Students
   - Fee Template
4. **Configure:**
   - Due Date
   - Payment Terms
5. Click "Generate Invoices"
6. System creates invoices for all selected students

---

## Fee Templates

### Creating Templates

1. Navigate to Fee Templates
2. Click "Create Template"
3. **Fill in:**
   - Name: e.g., "Term 1 Fees 2026"
   - Fee Items:
     - Tuition Fee
     - Library Fee
     - Sports Fee
     - etc.
   - Amounts for each item
4. Click "Save"

**Use:** Templates can be reused for bulk invoice creation.

---

## Payment Processing

### Mobile Money Payment

**How It Works:**
1. Parent receives invoice
2. Parent pays via MTN Mobile Money or Orange Money
3. Parent uploads payment proof
4. Finance staff verifies payment
5. Payment recorded in system
6. Invoice status updated to "PAID"

**Steps for Finance:**
1. Navigate to Payments
2. Review payment proofs
3. Verify transaction reference
4. Match amount to invoice
5. Approve payment
6. System updates invoice status

---

### Bank Transfer Payment

**How It Works:**
1. Parent receives invoice with bank details
2. Parent transfers funds
3. Parent uploads bank receipt
4. Finance staff verifies
5. Payment recorded

---

### Cash Payment

**How It Works:**
1. Parent pays at school office
2. Finance staff records payment
3. Receipt generated
4. Invoice status updated

---

## Payment Reconciliation

### Automatic Reconciliation

**How It Works:**
- System matches payment proofs to invoices
- Verifies transaction references
- Updates invoice status automatically
- Flags discrepancies for review

### Manual Reconciliation

**When to Use:**
- Automatic matching failed
- Payment proof unclear
- Need manual verification

**Steps:**
1. Navigate to Payment Reconciliation
2. Review unmatched payments
3. Match to invoice manually
4. Verify amount
5. Approve reconciliation

---

## Fee Reminders

### Automatic Reminders

**Setup:**
1. Navigate to Payment Reminders
2. Configure:
   - Days before due date
   - Reminder frequency
   - Message template
3. Enable automatic reminders

**How It Works:**
- System sends reminders automatically
- Based on due date
- Configurable frequency

---

### Manual Reminders

**Steps:**
1. Navigate to Overdue Invoices
2. Select invoices
3. Click "Send Reminders"
4. System sends to parents

---

## Financial Reports

### Available Reports

1. **Revenue Report:**
   - Total fees collected
   - By term/month
   - By fee type

2. **Outstanding Fees:**
   - Unpaid invoices
   - By student/classroom
   - By due date

3. **Payment History:**
   - All payments
   - By student
   - By date range

4. **Fee Collection Rate:**
   - Percentage collected
   - By term
   - By classroom

---

## Mobile Money Integration

### MTN Mobile Money

**Setup:**
1. Navigate to Site Settings → Integrations
2. Configure MTN Mobile Money:
   - API Key
   - Merchant ID
   - Webhook URL
3. Test connection

**How It Works:**
- Parent selects "Pay via MTN MoMo"
- Redirected to MTN payment page
- Payment processed
- Webhook confirms payment
- System updates invoice

---

### Orange Money

**Setup:**
1. Navigate to Site Settings → Integrations
2. Configure Orange Money:
   - API credentials
   - Merchant details
3. Test connection

---

## Common Issues

### Issue: Payment not recorded
**Solution:** Check payment proof uploaded and verify transaction reference.

### Issue: Invoice still showing as unpaid
**Solution:** Verify payment reconciliation completed and invoice status updated.

### Issue: Mobile money payment failed
**Solution:** Check integration settings and verify API credentials.

---

## Related Documentation

- Invoice Management Guide
- Payment Processing Guide
- Mobile Money Setup
- Financial Reporting Guide
