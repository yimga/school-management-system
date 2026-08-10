"""Seal: the finance money-center MAIN column is a single full-width column.

Bug (2026-08-10): on gilead-tech.runmycampus.com/finance/ the "Invoice status"
and "Invoice trend (4 months)" chart cards rendered as narrow vertical slivers
(the "No data to display" label wrapped one character per line) with the whole
right half of the page empty.

Root cause was purely CSS. `templates/finance/dashboard.html` wraps the finance
widget in `<div data-dashboard-column="main">`; that widget's two visible
children are the KPI `<section class="row">` (4 tiles) and the two-chart
`.dashboard-card-grid--charts` block. `rmc-tenant-configuration-operations.css`
forced `.rmc-finance-canvas [data-dashboard-column="main"]` to
`grid-template-columns: repeat(4, minmax(0, 1fr))`, so those two blocks crammed
into the left two of four cells and the charts sub-grid then split its ~25%-page
cell into two -> each chart ~12% of the page. Cells 3-4 sat empty.

Fix: make the main column a single full-width column. The KPI section lays its
own tiles 4-across (col-lg-3) and the charts block renders 2-up wide, matching
the Recent Invoices / Recent Payments pair below.

Pure text assertion over the shipped CSS -> SimpleTestCase, no DB (the test
harness can't create tenant schemas anyway). Must-fire: the pre-fix rule body
contained `repeat(4`, which `assertNotIn` rejects.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

_CSS = (
    Path(__file__).resolve().parents[3]
    / "static"
    / "css"
    / "rmc-tenant-configuration-operations.css"
)


def _one_line_rule_body(css: str, selector: str) -> str:
    """Return the `{...}` body of the single-selector, single-line rule.

    Matches `<selector> { ... }` where the declaration block sits on the same
    line and the selector is immediately followed by `{`. This deliberately
    does NOT match the media-query selector-list (where `main"]` is followed by
    a comma) or the `> *` child rule (where `main"]` is followed by ` > *`).
    """
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m is not None, f"rule not found for selector: {selector}"
    return m.group(1)


class FinanceMainColumnFillTest(SimpleTestCase):
    def test_main_column_is_single_full_width_column_not_four_col_grid(self):
        css = _CSS.read_text(encoding="utf-8")
        body = _one_line_rule_body(
            css, '.rmc-finance-canvas [data-dashboard-column="main"]'
        )
        # The bug: a 4-col grid crammed the KPI + charts blocks into the left
        # half and crushed the charts. Must be a single full-width column.
        self.assertNotIn("repeat(4", body, "main column must not be a 4-col grid")
        self.assertNotIn(
            "repeat(", body, "main column must not be any multi-track repeat() grid"
        )
        self.assertIn(
            "minmax(0, 1fr)", body, "main column should be a single minmax(0, 1fr) track"
        )

    def test_charts_block_stays_two_up_wide(self):
        # With the main column full-width, the invoice status/trend charts render
        # 2-up (each ~50% of the canvas), matching Recent Invoices/Payments.
        css = _CSS.read_text(encoding="utf-8")
        body = _one_line_rule_body(
            css, ".rmc-finance-canvas .dashboard-card-grid--charts"
        )
        self.assertIn("repeat(2, minmax(0, 1fr))", body)
