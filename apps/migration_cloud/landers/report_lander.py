"""Report lander — a DELIBERATE no-op for derived statistics reports.

A school's export set often includes a derived analytics file — ``school_stats``
with per-class / per-specialty aggregates (Total / Pass % / Passed / Male /
Female). Those are computed summaries, not per-entity records; ingesting them
fabricates one phantom enrollment row per aggregate line. Such artifacts are
detected up front (``accelerators.runmycampus_canonical.is_derived_report``) and
routed here, where every row is SKIPPED — the file is retained in the bundle as
a reference artifact but lands zero records.

This keeps the "no data is ever dropped" invariant honest: the report is not
lost (it stays attached to the bundle), it is simply not mis-ingested as data.
"""

from __future__ import annotations

from typing import Any, Iterator

from .base import Lander, LanderContext, LanderResult, register


class ReportLander(Lander):
    domain = "reports"

    def land(
        self,
        *,
        canonical_rows: Iterator[dict[str, Any]],
        ctx: LanderContext,
    ) -> LanderResult:
        result = LanderResult()
        for _row in canonical_rows:
            # Intentionally skipped: a derived-report aggregate line is not an
            # entity record. Counting it as skipped (not quarantined) makes the
            # operator summary read "N rows skipped — derived statistics report".
            result.skipped += 1
        return result


register("reports", ReportLander())
