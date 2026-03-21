"""RESILIENT_EDGE: finance templates load form-draft-save before FormDraftSave.init."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class FinanceFormDraftTemplateTests(SimpleTestCase):
    def _read(self, *parts: str) -> str:
        return (Path(settings.BASE_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_invoice_detail_loads_draft_script_and_keys(self):
        text = self._read("templates", "finance", "invoice_detail.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn('id="invoice-detail-main-form"', text)
        self.assertIn('data-draft-key="invoice_detail_main_', text)
        self.assertIn('data-draft-key="invoice_receipt_upload_', text)
        idx = text.index("form-draft-save.js")
        self.assertIn("FormDraftSave.init", text[idx:])

    def test_cash_office_closure_form_draft_wired(self):
        text = self._read("templates", "finance", "cash_office_closure.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("cash-office-closure-form", text)
        self.assertIn("closure_profile_id", text)

    def test_generate_fees_form_draft_wired(self):
        text = self._read("templates", "finance", "generate_fees.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("generate-fees-form", text)
        self.assertIn("generate_fees_", text)

    def test_access_bulk_form_draft_wired(self):
        text = self._read("templates", "finance", "access_bulk.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("finance-access-bulk-form", text)
        self.assertIn("finance_access_bulk_", text)
        idx = text.index("form-draft-save.js")
        self.assertIn("FormDraftSave.init", text[idx:])

    def test_suspense_queue_claim_forms_draft_wired(self):
        text = self._read("templates", "finance", "suspense_queue.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("suspense-claim-form-", text)
        self.assertIn("suspense_claim_", text)
        self.assertIn("form.suspense-claim-form[data-draft-key]", text)

    def test_payments_filter_form_draft_wired(self):
        text = self._read("templates", "finance", "payments.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("finance-payments-filter-form", text)
        self.assertIn("finance_payments_filter_", text)

    def test_scan_teller_form_draft_wired(self):
        text = self._read("templates", "finance", "scan_teller_placeholder.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("scan-teller-form", text)
        self.assertIn("finance_scan_teller_", text)

    def test_trial_balance_filter_form_draft_wired(self):
        text = self._read("templates", "finance", "trial_balance.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("trial-balance-filter-form", text)
        self.assertIn("trial_balance_filter_", text)

    def test_invoices_filter_form_draft_wired(self):
        text = self._read("templates", "finance", "invoices.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("finance-invoices-filter-form", text)
        self.assertIn("finance_invoices_filter_", text)

    def test_reports_period_and_request_forms_draft_wired(self):
        text = self._read("templates", "finance", "reports.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("finance-reports-period-form", text)
        self.assertIn("finance_reports_period_", text)
        self.assertIn("finance-report-request-form", text)
        self.assertIn("finance_report_request_", text)

    def test_finance_requests_inbox_form_draft_wired(self):
        text = self._read("templates", "finance", "requests.html")
        self.assertIn("form-draft-save.js", text)
        self.assertIn("finance-requests-inbox-form", text)
        self.assertIn("finance_requests_inbox_", text)

    def test_split_allocation_table_headers_have_scope_col(self):
        text = self._read("templates", "finance", "split_allocation.html")
        self.assertGreaterEqual(text.count('scope="col"'), 4)

    def test_expense_vs_budget_table_headers_have_scope_col(self):
        text = self._read("templates", "finance", "expense_vs_budget.html")
        self.assertIn('scope="col">Academic Year', text)
        self.assertIn('scope="col" class="text-end">Budget lines', text)

    def test_bursar_entries_report_table_headers_have_scope_col(self):
        text = self._read("templates", "finance", "bursar_entries_report.html")
        self.assertGreaterEqual(text.count('scope="col"'), 4)

    def test_printable_receipt_accessible_logo_and_table_label(self):
        """N23 / N3: standalone receipt uses translatable logo alt + table aria-label."""
        text = self._read("templates", "finance", "receipt.html")
        self.assertIn("{% load i18n region_format %}", text)
        self.assertIn("alt=\"{% trans 'School logo' %}\"", text)
        self.assertIn("aria-label=\"{% trans 'Invoice line items and amount paid' %}\"", text)
        self.assertIn('scope="col">Description</th>', text)
        self.assertIn('scope="row"', text)

    def test_receipt_print_template_table_scopes_and_lang(self):
        """N3: print/PDF receipt is a standalone HTML document with table semantics."""
        text = self._read("templates", "finance", "receipt.html")
        self.assertIn('scope="col">Description', text)
        self.assertIn('scope="col" class="text-right">Amount', text)
        self.assertIn('scope="row" class="total">Amount paid', text)
        self.assertIn('lang="{{ LANGUAGE_CODE|default:', text)
