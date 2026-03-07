# Global Ledger (Section 15.3)

Multi-currency, VAT/GST, scholarships, payment plans, installments, double-entry.

**Ref:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md § 15.3.

---

## 1. Current implementation

- **Finance models:** Invoice, Payment, FeeInstallment (finance.models). Ledger posting: LedgerAccount, ledger lines (compliance/finance); post_invoice_to_ledger, post_payment_to_ledger (finance.services). OHADA-style reports (ohada_reports.py).
- **Payment plans:** PaymentPlan, RecurringPaymentSubscription (finance.advanced_payments); InstallmentPlan for invoice installments.
- **Scholarship / aid:** Aid application and disbursement; post_scholarship_disbursement_to_ledger.

---

## 2. Multi-currency and tax

- **Multi-currency:** School/region currency; invoice and payment in currency; conversion when needed (section_28).
- **VAT/GST:** Tax engine and line items on invoices (partial; extend per region).

---

## 3. Implementation status

| Item | Status |
|------|--------|
| Double-entry / ledger posting | Done (finance.services, LedgerAccount) |
| Payment plans, installments | Done (PaymentPlan, InstallmentPlan, FeeInstallment) |
| Multi-currency | Partial (currency on models; conversion scoped) |
| VAT/GST / tax engine | Partial (extend per region) |
