"""v4.00.84 Wave 16 Target 3 — Per-tenant OAuth metrics smoke.

Validates ``apps/integrations_marketplace/lms_oauth_metrics.py``:

  1. Reset both global + per-tenant counters.
  2. record_refresh_attempt_for_tenant(canvas, acme, ok=True) x3
  3. record_refresh_attempt_for_tenant(canvas, beta_corp, ok=False, reason=expired_token) x1
  4. record_refresh_attempt_for_tenant(moodle, acme, ok=True) x2
  5. Global snapshot aggregates: canvas attempts == 4
  6. Per-tenant snapshot: canvas|acme attempts == 3
  7. Per-tenant snapshot: canvas|beta_corp failed == 1 + last_failure_reason
  8. Prometheus output contains BOTH global + per-tenant lines
  9. reset_oauth_metrics_per_tenant() clears only per-tenant
 10. After per-tenant reset: Prometheus emits global, no per-tenant block

Run:
    python scripts/smoke_v4_00_84_T3_per_tenant_metrics.py
"""
from __future__ import annotations

import os
import sys

# Ensure repo root is on sys.path when invoked from anywhere.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Minimal Django settings hook (the module lazily imports django.utils.timezone
# but falls back to stdlib datetime if Django isn't configured, so this is
# best-effort).
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
try:
    import django  # noqa: WPS433
    django.setup()
except Exception:  # noqa: BLE001
    pass

from apps.integrations_marketplace import lms_oauth_metrics as M  # noqa: E402

PASS = 0
FAIL = 0


def _check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  OK  {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label} {detail}")


def case_1_reset_baseline() -> None:
    print("[1] reset both counters")
    M.reset_oauth_metrics()
    M.reset_oauth_metrics_per_tenant()
    _check("global empty", M.get_oauth_metrics_snapshot() == {})
    _check("per-tenant empty", M.get_oauth_metrics_per_tenant_snapshot() == {})


def case_2_canvas_acme_ok_x3() -> None:
    print("[2] canvas/acme ok x3")
    for _ in range(3):
        M.record_refresh_attempt_for_tenant(provider="canvas", tenant_schema="acme", ok=True)
    snap = M.get_oauth_metrics_per_tenant_snapshot()
    _check("canvas|acme present", "canvas|acme" in snap)
    _check("canvas|acme attempts==3", snap.get("canvas|acme", {}).get("attempts") == 3)
    _check("canvas|acme ok==3", snap.get("canvas|acme", {}).get("ok") == 3)
    _check("canvas|acme failed==0", snap.get("canvas|acme", {}).get("failed") == 0)


def case_3_canvas_beta_failed_x1() -> None:
    print("[3] canvas/beta_corp failed x1 expired_token")
    M.record_refresh_attempt_for_tenant(
        provider="canvas", tenant_schema="beta_corp", ok=False, reason="expired_token"
    )
    snap = M.get_oauth_metrics_per_tenant_snapshot()
    _check("canvas|beta_corp present", "canvas|beta_corp" in snap)
    _check("canvas|beta_corp failed==1", snap.get("canvas|beta_corp", {}).get("failed") == 1)


def case_4_moodle_acme_ok_x2() -> None:
    print("[4] moodle/acme ok x2")
    for _ in range(2):
        M.record_refresh_attempt_for_tenant(provider="moodle", tenant_schema="acme", ok=True)
    snap = M.get_oauth_metrics_per_tenant_snapshot()
    _check("moodle|acme present", "moodle|acme" in snap)
    _check("moodle|acme attempts==2", snap.get("moodle|acme", {}).get("attempts") == 2)


def case_5_global_aggregates_canvas_4() -> None:
    print("[5] global snapshot aggregates across tenants — canvas attempts==4")
    gsnap = M.get_oauth_metrics_snapshot()
    _check("canvas in global", "canvas" in gsnap)
    _check("canvas attempts==4", gsnap.get("canvas", {}).get("attempts") == 4,
           detail=f"actual={gsnap.get('canvas', {}).get('attempts')}")
    _check("canvas ok==3", gsnap.get("canvas", {}).get("ok") == 3)
    _check("canvas failed==1", gsnap.get("canvas", {}).get("failed") == 1)
    _check("moodle attempts==2", gsnap.get("moodle", {}).get("attempts") == 2)


def case_6_per_tenant_canvas_acme_3() -> None:
    print("[6] per-tenant canvas|acme attempts==3")
    snap = M.get_oauth_metrics_per_tenant_snapshot()
    _check("canvas|acme attempts==3", snap.get("canvas|acme", {}).get("attempts") == 3)


def case_7_per_tenant_canvas_beta_reason() -> None:
    print("[7] per-tenant canvas|beta_corp failed==1 + last_failure_reason")
    snap = M.get_oauth_metrics_per_tenant_snapshot()
    row = snap.get("canvas|beta_corp", {})
    _check("canvas|beta_corp failed==1", row.get("failed") == 1)
    _check(
        'canvas|beta_corp last_failure_reason=="expired_token"',
        row.get("last_failure_reason") == "expired_token",
        detail=f"actual={row.get('last_failure_reason')!r}",
    )


def case_8_prometheus_both_blocks() -> None:
    print("[8] Prometheus output has BOTH global + per-tenant lines")
    text = M.render_prometheus_metrics()
    global_line = 'rmc_lms_oauth_refresh_attempts_total{provider="canvas"} 4'
    tenant_line = 'rmc_lms_oauth_refresh_attempts_by_tenant_total{provider="canvas",tenant="acme"} 3'
    _check("global canvas line present", global_line in text,
           detail=f"missing: {global_line!r}")
    _check("per-tenant canvas|acme line present", tenant_line in text,
           detail=f"missing: {tenant_line!r}")
    _check(
        "per-tenant HELP block present",
        "# HELP rmc_lms_oauth_refresh_attempts_by_tenant_total" in text,
    )


def case_9_reset_per_tenant_only() -> None:
    print("[9] reset_oauth_metrics_per_tenant() clears per-tenant only")
    M.reset_oauth_metrics_per_tenant()
    _check("per-tenant empty", M.get_oauth_metrics_per_tenant_snapshot() == {})
    gsnap = M.get_oauth_metrics_snapshot()
    _check("global canvas still 4", gsnap.get("canvas", {}).get("attempts") == 4)
    _check("global moodle still 2", gsnap.get("moodle", {}).get("attempts") == 2)


def case_10_prometheus_after_reset() -> None:
    print("[10] After per-tenant reset, Prometheus still emits global, no per-tenant block")
    text = M.render_prometheus_metrics()
    global_line = 'rmc_lms_oauth_refresh_attempts_total{provider="canvas"} 4'
    _check("global canvas line still present", global_line in text)
    _check(
        "per-tenant HELP block absent",
        "rmc_lms_oauth_refresh_attempts_by_tenant_total" not in text,
        detail="per-tenant block leaked after reset",
    )


def main() -> int:
    print("=" * 70)
    print("v4.00.84 Wave 16 Target 3 — Per-tenant OAuth metrics smoke")
    print("=" * 70)
    case_1_reset_baseline()
    case_2_canvas_acme_ok_x3()
    case_3_canvas_beta_failed_x1()
    case_4_moodle_acme_ok_x2()
    case_5_global_aggregates_canvas_4()
    case_6_per_tenant_canvas_acme_3()
    case_7_per_tenant_canvas_beta_reason()
    case_8_prometheus_both_blocks()
    case_9_reset_per_tenant_only()
    case_10_prometheus_after_reset()
    print("=" * 70)
    print(f"PASS={PASS} FAIL={FAIL}")
    print("=" * 70)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
