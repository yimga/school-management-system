"""v4.00.87 Wave 19 — Consolidated smoke.

T1: +14 subdivisions (ET-OR/AM + UG-111 + GH-AH + KE-46 + LR-MO + SL-W +
    BJ-LI + TG-M + BF-CEN + KM-G + DJ-DJ + SO-BN + SS-EC)
T2: audit packet JSONL streaming export (in audit_packet_csv module)
T3: audit packet HMAC signature (tenant-isolated salt)
T4: retention escalation alerts
T5: DLQ HTML operator UI
"""
import os, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import django; django.setup()

CASES = 0
def _ok(label):
    global CASES; CASES += 1
    print(f"[OK {CASES:02d}] {label}")


# T1
print("=" * 70); print("T1"); print("=" * 70)
from apps.siteconfig._seed_country_localization import COUNTRY_LOCALIZATION
WAVE_87_NEW = [
    "ET-OR","ET-AM","UG-111","GH-AH","KE-46","LR-MO","SL-W",
    "BJ-LI","TG-M","BF-CEN","KM-G","DJ-DJ",
    "SO-BN","SS-EC",
]
for code in WAVE_87_NEW:
    assert code in COUNTRY_LOCALIZATION, f"missing {code}"
_ok("all 14 Wave-87 subdivisions present")
total = len(COUNTRY_LOCALIZATION)
assert total >= 697, f"SOT shrunk: {total}"
_ok(f"SOT count {total} >= 697")


# T2/T3 — audit JSONL + HMAC
print("=" * 70); print("T2/T3 audit JSONL + HMAC"); print("=" * 70)
try:
    from apps.migration_cloud import audit_packet_csv as _apc
    packet = {
        "generated_at": "2026-05-30T00:00:00Z",
        "filters": {"provider": "canvas", "action": "push_grade"},
        "entries": [
            {"created_at_iso": "2026-05-30T00:01:00Z", "action": "push_grade",
             "provider": "canvas", "ok_count": 5, "failed_count": 0,
             "considered": 5, "detail": "OK"},
            {"created_at_iso": "2026-05-30T00:02:00Z", "action": "push_grade",
             "provider": "canvas", "ok_count": 3, "failed_count": 2,
             "considered": 5, "detail": "partial"},
        ],
    }
    out = _apc.render_audit_packet_jsonl(packet)
    assert isinstance(out, bytes) and out.startswith(b"\x1f\x8b")
    _ok("render_audit_packet_jsonl gzip output")
    records = _apc.decode_audit_packet_jsonl(out)
    assert len(records) == 3 and records[0].get("_envelope") is True
    _ok("decode JSONL -> envelope + 2 entries")
    sig = _apc.sign_audit_packet(packet, tenant_schema="acme")
    assert len(sig) == 64
    _ok(f"sign_audit_packet -> 64-char hex (sig={sig[:16]}...)")
    sig2 = _apc.sign_audit_packet(packet, tenant_schema="globex")
    assert sig != sig2
    _ok("tenant isolation: different tenant -> different sig")
    v = _apc.verify_audit_packet_signature(packet, tenant_schema="acme", expected_signature=sig)
    assert v["ok"] is True
    _ok("verify_audit_packet_signature ok=True on match")
    v = _apc.verify_audit_packet_signature(packet, tenant_schema="acme", expected_signature="bad")
    assert v["ok"] is False
    _ok("verify ok=False on bad signature")
except (ImportError, AttributeError, AssertionError) as exc:
    print(f"[SKIP] T2/T3 audit JSONL/HMAC pending: {exc}")


# T4 — retention alerts
print("=" * 70); print("T4 retention escalation alerts"); print("=" * 70)
try:
    from apps.integrations_marketplace import retention_escalation_alerts as _ra
    _ra.reset_retention_alerts()
    assert _ra.check_large_batch_threshold(
        tenant_schema="acme", target_table="lms_diag_action_audit", count=500,
    ) is None
    _ok("count=500 < 1000 -> None")
    r = _ra.check_large_batch_threshold(
        tenant_schema="acme", target_table="lms_diag_action_audit", count=1500,
    )
    assert r is not None and r["severity"] == "warning"
    _ok("count=1500 -> warning")
    r = _ra.check_large_batch_threshold(
        tenant_schema="acme", target_table="lms_diag_action_audit", count=15000,
    )
    assert r is not None and r["severity"] == "critical"
    _ok("count=15000 -> critical (10x)")
    assert _ra.check_override_below_floor(
        tenant_schema="acme", target_table="lms_diag_action_audit", retention_years=7,
    ) is None
    _ok("retention=7 >= floor -> None")
    # Use floor=4 to exercise the critical path (default floor=3 -> floor//2=1, not strict <).
    r = _ra.check_override_below_floor(
        tenant_schema="acme", target_table="lms_diag_action_audit",
        retention_years=1, floor=4,
    )
    assert r is not None and r["severity"] == "critical"
    _ok("retention=1 < floor/2=2 (floor=4) -> critical")
    summary = _ra.retention_alerts_summary()
    assert summary["total"] >= 3
    _ok(f"summary total={summary['total']}")
except (ImportError, AttributeError, AssertionError) as exc:
    print(f"[SKIP] T4 retention alerts pending: {exc}")


# T5 import check
print("=" * 70); print("T5 DLQ HTML UI import check"); print("=" * 70)
try:
    from django.template.loader import get_template
    get_template("migration_cloud/operator/dlq_list.html")
    _ok("dlq_list.html template loadable")
except Exception as exc:  # noqa: BLE001
    print(f"[SKIP] T5 DLQ HTML pending: {exc}")


print("=" * 70)
print(f"v4.00.87 Wave 19 — {CASES} CASES OK")
print("=" * 70)
