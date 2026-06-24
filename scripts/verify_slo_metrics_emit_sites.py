#!/usr/bin/env python3
"""Verify SLO metric emit sites wire slo.py objectives to the metrics bridge (T2/T3 live)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REQUIRED_TXN_SITES = (
    "auth.login",
    "attendance.submit",
    "grade.entry",
    "parent.dashboard.render",
    "finance.invoice.create",
    "finance.payment.record",
    "webhook.deliver",
    "ai.gateway.invoke",
    "migration.bundle_apply",
    "sync.delta_apply",
)


def _fail(msg: str) -> None:
    print(f"SLO_METRICS_EMIT_SITES_FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def main() -> int:
    slo_metrics = ROOT / "apps/observability/slo_metrics.py"
    if not slo_metrics.is_file():
        _fail("missing apps/observability/slo_metrics.py")
    ast.parse(slo_metrics.read_text(encoding="utf-8"))

    sm_text = _read("apps/observability/slo_metrics.py")
    for fn in (
        "record_slo_outcome",
        "record_web_availability",
        "record_traced_transaction",
        "TRANSACTION_TO_SLO",
    ):
        if fn not in sm_text:
            _fail(f"slo_metrics.py missing {fn!r}")

    tracing = _read("apps/observability/tracing.py")
    if "record_traced_transaction" not in tracing:
        _fail("tracing.py must call record_traced_transaction on finish")
    if "_TraceHandle" not in tracing:
        _fail("tracing.py missing _TraceHandle for SLO timing")

    middleware = _read("apps/observability/middleware.py")
    if "record_web_availability" not in middleware:
        _fail("ObservabilityMiddleware missing record_web_availability")

    tree_text = "\n".join(
        _read(path) for path in (
            "apps/accounts/views.py",
            "apps/academics/api_views.py",
            "apps/evals/views.py",
            "apps/portal/views_parent.py",
            "apps/finance/api_views.py",
            "apps/events/webhooks.py",
            "services/ai_gateway.py",
            "apps/migration_cloud/orchestrator.py",
            "apps/api/sync_services.py",
        )
    )
    for txn in REQUIRED_TXN_SITES:
        if txn not in tree_text:
            _fail(f"expected trace site for transaction {txn!r} missing from hot paths")

    from apps.observability.slo_metrics import TRANSACTION_TO_SLO, slo_key_for_transaction

    for txn in REQUIRED_TXN_SITES:
        if slo_key_for_transaction(txn) is None and txn != "http.server":
            # grade.entry etc. must map via @trace_view name == sentry_transactions entry
            if txn not in TRANSACTION_TO_SLO:
                _fail(f"TRANSACTION_TO_SLO missing {txn!r}")

    alerts = ROOT / "deploy/observability/slo_alerts.yml"
    if not alerts.is_file() or "failures_total" not in alerts.read_text(encoding="utf-8"):
        _fail("deploy/observability/slo_alerts.yml missing or stale")

    print("SLO_METRICS_EMIT_SITES_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
