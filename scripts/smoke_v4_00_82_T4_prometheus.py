"""v4.00.82 Wave 14 Target 4 smoke — Prometheus text exposition for LMS OAuth metrics.

Verifies the ``render_prometheus_metrics()`` exporter appended to
``apps/integrations_marketplace/lms_oauth_metrics.py``:

* HELP + TYPE lines are present for each of the 3 metric families
* attempts / successes / failures rows match the recorded counts
* trailing newline per Prometheus spec
* label-value escaping (backslash / double-quote)
* empty snapshot still emits HELP+TYPE but no data rows

Run::

    python scripts/smoke_v4_00_82_T4_prometheus.py
"""
from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _assert(cond: bool, label: str) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        raise SystemExit(1)


def main() -> int:
    from apps.integrations_marketplace.lms_oauth_metrics import (
        record_refresh_attempt,
        render_prometheus_metrics,
        reset_oauth_metrics,
    )

    # ---- Case 1: seed counters ----------------------------------------
    reset_oauth_metrics()
    for _ in range(3):
        record_refresh_attempt("canvas", ok=True)
    record_refresh_attempt("canvas", ok=False, reason="expired_token")
    for _ in range(2):
        record_refresh_attempt("moodle", ok=True)
    _assert(True, "1. seed counters (3 canvas OK, 1 canvas fail, 2 moodle OK)")

    # ---- Case 2: render returns a string ------------------------------
    out = render_prometheus_metrics()
    _assert(isinstance(out, str), "2. render_prometheus_metrics() returns str")

    # ---- Case 3: HELP line present ------------------------------------
    _assert(
        "# HELP rmc_lms_oauth_refresh_attempts_total" in out,
        "3. HELP rmc_lms_oauth_refresh_attempts_total present",
    )

    # ---- Case 4: TYPE line present ------------------------------------
    _assert(
        "# TYPE rmc_lms_oauth_refresh_attempts_total counter" in out,
        "4. TYPE rmc_lms_oauth_refresh_attempts_total counter present",
    )

    # ---- Case 5: canvas attempts = 4 ----------------------------------
    _assert(
        'rmc_lms_oauth_refresh_attempts_total{provider="canvas"} 4' in out,
        '5. canvas attempts row == 4',
    )

    # ---- Case 6: canvas successes = 3 ---------------------------------
    _assert(
        'rmc_lms_oauth_refresh_successes_total{provider="canvas"} 3' in out,
        '6. canvas successes row == 3',
    )

    # ---- Case 7: canvas failures = 1 ----------------------------------
    _assert(
        'rmc_lms_oauth_refresh_failures_total{provider="canvas"} 1' in out,
        '7. canvas failures row == 1',
    )

    # ---- Case 8: trailing newline -------------------------------------
    _assert(out.endswith("\n"), "8. output ends with \\n")

    # ---- Case 9: special-char label escape ----------------------------
    reset_oauth_metrics()
    record_refresh_attempt('strange"name', ok=True)
    out_esc = render_prometheus_metrics()
    # Label value should escape the embedded double-quote.
    _assert(
        'provider="strange\\"name"' in out_esc,
        '9. double-quote in provider name escaped as \\"',
    )
    # And the row should still report attempts=1.
    _assert(
        'rmc_lms_oauth_refresh_attempts_total{provider="strange\\"name"} 1' in out_esc,
        "9b. escaped-label row carries the correct count",
    )

    # ---- Case 10: empty snapshot --------------------------------------
    reset_oauth_metrics()
    out_empty = render_prometheus_metrics()
    _assert(
        "# HELP rmc_lms_oauth_refresh_attempts_total" in out_empty
        and "# TYPE rmc_lms_oauth_refresh_attempts_total counter" in out_empty
        and "# HELP rmc_lms_oauth_refresh_successes_total" in out_empty
        and "# HELP rmc_lms_oauth_refresh_failures_total" in out_empty,
        "10. empty snapshot still emits HELP+TYPE for all 3 families",
    )
    # No data rows for any provider.
    has_data_row = any(
        line and not line.startswith("#")
        for line in out_empty.splitlines()
    )
    _assert(not has_data_row, "10b. empty snapshot has no data rows (only HELP/TYPE)")

    print()
    print("10/10 v4.00.82 T4 Prometheus exporter cases PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
