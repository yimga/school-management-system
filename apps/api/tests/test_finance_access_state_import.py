"""Backlog fix (2026-06-10) — finance access gate imports the real module.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

``_require_parent_finance_or_operator_access`` (apps/api/views_v1.py) did an
unguarded ``from apps.finance.views import _finance_access_state`` — but that
helper lives in ``apps.finance.views_common`` (and is NOT re-exported from
``finance.views``). So for a PARENT user the import raised ImportError -> 500 on
every finance endpoint guarded by it, including the routed FinanceWalletTopUpView
(api/urls_v1.py). Staff/operators pass an earlier branch, so it was parent-only.

Fixed to import from apps.finance.views_common.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

REPO = pathlib.Path(__file__).resolve().parent.parent.parent.parent


class FinanceAccessStateImportTests(unittest.TestCase):

    def test_gate_imports_from_views_common(self) -> None:
        src = (REPO / "apps" / "api" / "views_v1.py").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn(
            "from apps.finance.views_common import _finance_access_state", src
        )
        self.assertNotIn(
            "from apps.finance.views import _finance_access_state", src
        )

    def test_real_helper_exists_with_expected_signature(self) -> None:
        from apps.finance.views_common import _finance_access_state

        params = inspect.signature(_finance_access_state).parameters
        self.assertIn("user", params)
        self.assertIn("request", params)

    def test_not_reexported_from_finance_views(self) -> None:
        # Documents WHY the module matters: finance.views does not expose it.
        import apps.finance.views as fv

        self.assertFalse(hasattr(fv, "_finance_access_state"))


if __name__ == "__main__":
    unittest.main()
