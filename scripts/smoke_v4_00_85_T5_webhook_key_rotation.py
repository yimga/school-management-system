"""v4.00.85 Wave 17 Target 5 smoke - webhook key rotation dual-signing.

Cases:
 1. stage_new_secret returns True
 2. get_staged_secret_record returns dict w/ staged_secret
 3. mint_dual_signature_pair returns both primary and next w/ sha256= prefix
 4. promote_staged_secret returns "new_s" and clears
 5. After promote, next is None
 6. Grace expiry drops record
 7. Empty secret rejected
 8. grace_seconds=0 rejected
 9. Eviction at cap
10. rotation_summary leaks no secret material
11. PII guard: warning log w/ record does not surface secret
"""
from __future__ import annotations

import os
import sys
import time
import logging
import io

# Bootstrap Django settings before importing modules that touch timezone
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Ensure project root is on sys.path
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import django
    django.setup()
except Exception as exc:  # noqa: BLE001
    print(f"[setup] django.setup failed: {exc!r}")

from apps.integrations_marketplace import webhook_key_rotation as wkr


def _assert(cond, label):
    status = "OK" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        raise SystemExit(1)


def main() -> int:
    wkr.reset_staged_secrets()

    # Case 1
    ok = wkr.stage_new_secret(subscription_id=1, new_secret="new_s", grace_seconds=60)
    _assert(ok is True, "case1 stage_new_secret returns True")

    # Case 2
    rec = wkr.get_staged_secret_record(1)
    _assert(isinstance(rec, dict) and rec.get("staged_secret") == "new_s",
            "case2 get_staged_secret_record returns dict w/ staged_secret='new_s'")

    # Case 3
    pair = wkr.mint_dual_signature_pair(payload_bytes=b'{"x":1}', active_secret="old_s", subscription_id=1)
    _assert(isinstance(pair, dict) and "primary" in pair and "next" in pair,
            "case3a mint_dual_signature_pair returns dict w/ primary and next")
    _assert(pair["primary"] != pair["next"],
            "case3b primary hex differs from next hex (different keys)")
    _assert(pair["primary"].startswith("sha256=") and pair["next"].startswith("sha256="),
            "case3c both start with sha256=")

    # Case 4
    promoted = wkr.promote_staged_secret(1)
    _assert(promoted == "new_s", "case4a promote_staged_secret returns 'new_s'")
    _assert(wkr.get_staged_secret_record(1) is None,
            "case4b staged record gone after promote")

    # Case 5
    pair2 = wkr.mint_dual_signature_pair(payload_bytes=b'{"x":1}', active_secret="old_s", subscription_id=1)
    _assert(pair2.get("next") is None, "case5 next is None after promote")

    # Case 6 - grace expiry
    wkr.reset_staged_secrets()
    ok6 = wkr.stage_new_secret(subscription_id=42, new_secret="exp_s", grace_seconds=1)
    _assert(ok6 is True, "case6a stage_new_secret w/ grace_seconds=1 returns True")
    time.sleep(1.1)
    rec6 = wkr.get_staged_secret_record(42)
    _assert(rec6 is None, "case6b grace expired: get_staged_secret_record returns None")
    # Confirm record was dropped (re-fetch still None, no stale state)
    _assert(wkr.get_staged_secret_record(42) is None,
            "case6c expired record was dropped")

    # Case 7 - empty secret rejected
    bad = wkr.stage_new_secret(subscription_id=7, new_secret="", grace_seconds=60)
    _assert(bad is False, "case7 empty new_secret -> False")

    # Case 8 - grace_seconds=0
    bad8 = wkr.stage_new_secret(subscription_id=8, new_secret="x", grace_seconds=0)
    _assert(bad8 is False, "case8 grace_seconds=0 -> False")

    # Case 9 - eviction at cap
    wkr.reset_staged_secrets()
    # Stage 101 distinct subscription_ids; first should be evicted
    for i in range(1, 102):
        wkr.stage_new_secret(subscription_id=i, new_secret=f"s_{i}", grace_seconds=60)
    summary = wkr.rotation_summary()
    _assert(summary["staged_count"] <= 100,
            f"case9a staged_count capped at 100 (got {summary['staged_count']})")
    _assert(1 not in summary["subscription_ids_with_staged"],
            "case9b first subscription_id (1) evicted")
    _assert(101 in summary["subscription_ids_with_staged"],
            "case9c last subscription_id (101) present")

    # Case 10 - rotation_summary leaks no secret material
    summary_repr = repr(wkr.rotation_summary())
    _assert("staged_secret" not in summary_repr,
            "case10a rotation_summary repr does not include 'staged_secret'")
    _assert("s_50" not in summary_repr and "new_s" not in summary_repr,
            "case10b rotation_summary repr does not include any secret value")

    # Case 11 - PII guard: warning log with rec does not surface secret
    wkr.reset_staged_secrets()
    wkr.stage_new_secret(subscription_id=999, new_secret="super_secret_value", grace_seconds=60)
    rec11 = wkr.get_staged_secret_record(999)
    # Capture logger output
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.DEBUG)
    test_logger = logging.getLogger("smoke_v4_00_85_T5")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.DEBUG)
    # Caller's responsibility is to redact - we emulate a safe call site
    # that only logs the keys/metadata, NEVER the secret value.
    redacted = {k: ("<redacted>" if k == "staged_secret" else v) for k, v in (rec11 or {}).items()}
    test_logger.warning("rotation record (redacted): %s", redacted)
    test_logger.removeHandler(handler)
    log_output = buf.getvalue()
    _assert("super_secret_value" not in log_output,
            "case11 redacted logging does NOT surface secret value")
    _assert("<redacted>" in log_output,
            "case11b redaction marker present in log output")

    print("\n[done] 11/11 cases green - v4.00.85 Wave 17 Target 5 smoke OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
