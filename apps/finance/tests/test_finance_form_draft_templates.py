"""RESILIENT_EDGE: finance templates load form-draft-save and declare draft keys.

Was "... before FormDraftSave.init". The CSP wave that retired inline event
handlers removed those calls and the library now auto-inits every
form[data-draft-key] on DOMContentLoaded, so the contract is the pair -- the
script is loaded and the form declares a key -- not an inline call site.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import assert_loads_static, assert_markup


class FinanceFormDraftTemplateTests(SimpleTestCase):
    def _assert_auto_init_draft_form(self, text: str, path=None) -> None:
        """The draft library is loaded and a form declares a draft key.

        This used to assert an inline FormDraftSave.init(...) after the
        <script>. The CSP wave that retired inline handlers removed the call
        and the library grew a DOMContentLoaded auto-init over every
        form[data-draft-key] -- its own source names the templates it is
        replacing. Asserting the call back would ask for the inline script
        that work deliberately deleted; the contract is the pair below.
        """
        self.assertIn("form-draft-save.js", text)
        self.assertIn("data-draft-key=", text)
        if path is not None:
            # The engine-backed halves: the {% static %} tag really loads the
            # library, and the form really EMITS a draft key. Without these the
            # test passes over a template whose whole body is a comment.
            assert_loads_static(self, path, "js/form-draft-save.js")
            assert_markup(self, path, "data-draft-key=")

    def _assert_column(self, text: str, token: str) -> None:
        """Some <th scope="col"> carries this label, however it is wrapped.

        Pinned as scope="col">Description and went red when the labels were
        wrapped in {% trans %} (and, for the academic year, a {% term %}
        tag). The scope never moved.
        """
        pattern = r'<th[^>]*scope="col"[^>]*>[^<]*' + re.escape(token)
        self.assertRegex(
            text, pattern, f'no <th scope="col"> carries {token!r}'
        )

    def _path(self, *parts: str) -> Path:
        return Path(settings.BASE_DIR).joinpath(*parts)

    def _read(self, *parts: str) -> str:
        return (Path(settings.BASE_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_invoice_detail_loads_draft_script_and_keys(self):
        text = self._read("templates", "finance", "invoice_detail.html")
        self._assert_auto_init_draft_form(
            text, self._path("templates", "finance", "invoice_detail.html")
        )
        self.assertIn('id="invoice-detail-main-form"', text)
        self.assertIn('data-draft-key="invoice_detail_main_', text)
        self.assertIn('data-draft-key="invoice_receipt_upload_', text)

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
        self._assert_auto_init_draft_form(
            text, self._path("templates", "finance", "access_bulk.html")
        )
        self.assertIn("finance-access-bulk-form", text)
        self.assertIn("finance_access_bulk_", text)

    def test_suspense_queue_claim_forms_draft_wired(self):
        text = self._read("templates", "finance", "suspense_queue.html")
        self._assert_auto_init_draft_form(
            text, self._path("templates", "finance", "suspense_queue.html")
        )
        self.assertIn("suspense-claim-form-", text)
        self.assertIn("suspense_claim_", text)
        # The selector moved out of the template with the inline handlers.
        page_js = (
            Path(settings.BASE_DIR)
            / "static/js/_pages/finance__suspense_queue.js"
        ).read_text(encoding="utf-8")
        self.assertIn("form.suspense-claim-form[data-draft-key]", page_js)

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
        # The year header is a {% term "academic_year" %} tag, not a msgid.
        self._assert_column(text, "academic_year")
        self._assert_column(text, "Budget lines")
        assert_markup(
            self, self._path("templates", "finance", "expense_vs_budget.html"),
            'scope="col"',
        )

    def test_bursar_entries_report_table_headers_have_scope_col(self):
        text = self._read("templates", "finance", "bursar_entries_report.html")
        self.assertGreaterEqual(text.count('scope="col"'), 4)

    def test_printable_receipt_accessible_logo_and_table_label(self):
        """N23 / N3: standalone receipt uses translatable logo alt + table aria-label."""
        text = self._read("templates", "finance", "receipt.html")
        # Pinned the whole {% load %} line, which then gained
        # terminology_tags. What matters is that both libraries are loaded.
        # The whole {% load %} line was pinned and then gained
        # terminology_tags. What the contract means is that both libraries are
        # loaded; the first tag on the page is that load.
        load_tag = text.split("%}", 1)[0]
        self.assertIn("i18n", load_tag)
        self.assertIn("region_format", load_tag)
        # The logo moved one include deeper, into the rmc-print-v2 brand block
        # ('civic brand block per rmc-print-v2 grammar', says the template's own
        # comment). The receipt no longer carries an <img> of its own, so assert
        # the wiring here and the accessible name where it now lives.
        self.assertIn("partials/rmc_print_v2_brand_block.html", text)
        brand_block = self._read(
            "templates", "partials", "rmc_print_v2_brand_block.html"
        )
        self.assertRegex(brand_block, r'<img[^>]*alt="\{%\s*trans')
        self.assertIn("aria-label=\"{% trans 'Invoice line items and amount paid' %}\"", text)
        self._assert_column(text, "Description")
        self.assertIn('scope="row"', text)

    def test_receipt_print_template_table_scopes_and_lang(self):
        """N3: print/PDF receipt is a standalone HTML document with table semantics."""
        text = self._read("templates", "finance", "receipt.html")
        self._assert_column(text, "Description")
        self._assert_column(text, "Amount")
        # The labels sit inside tags, so the checks above must read the
        # source -- which a commented-out template satisfies. Pair them with
        # the one thing the ENGINE can see here: the scope attributes.
        assert_markup(
            self, self._path("templates", "finance", "receipt.html"),
            'scope="col"', 'scope="row"',
        )
        self.assertRegex(
            text,
            r'<th[^>]*scope="row"[^>]*>[^<]*' + re.escape("Amount paid"),
            'no <th scope="row"> carries the total row label',
        )
        self.assertIn('lang="{{ LANGUAGE_CODE|default:', text)
