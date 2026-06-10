"""Workflow 7 (Payments) — offline-intent CSV export currency source.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

Guards the 2026-06-10 fix: ``offline_payment_intent_queue_export`` wrote
``intent.currency_code`` into the CSV, but ``OfflinePaymentIntent`` has NO
currency field — it raised AttributeError, 500-ing the bursar's CSV export.
The currency belongs to the school's compliance profile (already resolved +
non-None in the view), so the export now uses ``profile.currency_code``.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = Path(__file__).resolve().parent.parent.parent.parent


class OfflineIntentExportCurrencyTests(unittest.TestCase):

    def test_intent_has_no_currency_field(self) -> None:
        from apps.finance.models import OfflinePaymentIntent

        names = {f.name for f in OfflinePaymentIntent._meta.get_fields()}
        self.assertNotIn("currency_code", names)

    def test_compliance_profile_has_currency(self) -> None:
        from apps.finance.models import ComplianceProfile

        names = {f.name for f in ComplianceProfile._meta.get_fields()}
        self.assertIn("currency_code", names)

    def test_export_view_uses_profile_currency_not_intent(self) -> None:
        src = (REPO / "apps" / "finance" / "views_offline_bursar_queue.py").read_text(
            encoding="utf-8", errors="replace"
        )
        # Active code writes the profile currency into the CSV row.
        self.assertIn('profile.currency_code or ""', src)
        # The buggy access form must not be live code (a prose mention of the
        # old bug in a comment is fine; the executable form is not).
        self.assertNotIn('intent.currency_code or ""', src)


if __name__ == "__main__":
    unittest.main()
