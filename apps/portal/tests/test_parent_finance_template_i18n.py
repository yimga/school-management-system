"""N2: parent finance template uses {% trans %} for user-visible copy."""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ParentFinanceTemplateI18nTests(SimpleTestCase):
    def test_finance_html_wraps_visible_strings_in_trans(self):
        text = (
            Path(settings.BASE_DIR)
            / "templates"
            / "parent"
            / "finance.html"
        ).read_text(encoding="utf-8")
        self.assertIn('{% trans "Finances" %}', text)
        self.assertIn('{% trans "Invoice attachments" %}', text)
        self.assertIn('{% trans "Request finance access" %}', text)
        self.assertIn('id="parent-finance-access-request-form"', text)
        self.assertIn('dir="auto"', text)
        self.assertTrue(
            '{% trans "Invoices" %}' in text
            or '{% trans_term "Invoices"' in text
            or 'trans_term "Invoices"' in text,
            "Invoices heading must use trans or trans_term",
        )
