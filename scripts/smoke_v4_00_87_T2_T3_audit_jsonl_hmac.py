"""v4.00.87 Wave 19 Targets 2 + 3 smoke — audit-packet JSONL + HMAC signature.

Validates:
  * T2: render_audit_packet_jsonl / decode_audit_packet_jsonl
  * T3: sign_audit_packet / verify_audit_packet_signature

No DB required — we hand-build fake packet dicts.
"""
from __future__ import annotations

import os
import sys


# Ensure repo root is on sys.path so ``apps.*`` imports resolve when the
# script is run directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


from apps.migration_cloud.audit_packet_csv import (  # noqa: E402
    render_audit_packet_csv,
    decode_audit_packet_csv,
    render_audit_packet_jsonl,
    decode_audit_packet_jsonl,
    sign_audit_packet,
    verify_audit_packet_signature,
    _DEFAULT_ROOT_FOR_TEST,
)


_RESULTS: list[tuple[str, bool, str]] = []


def _check(name: str, ok: bool, note: str = "") -> None:
    _RESULTS.append((name, ok, note))
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}{(' — ' + note) if note else ''}")


def _fake_packet(n_entries: int = 3, detail: str = "") -> dict:
    entries = []
    for i in range(n_entries):
        entries.append({
            "ts_iso": f"2026-05-30T10:0{i}:00+00:00",
            "actor_hash": f"abcdef{i:06d}",
            "action": ["force_refresh", "force_rotate", "retention_purge"][i % 3],
            "provider": ["canvas", "google_classroom", "schoology"][i % 3],
            "considered": 10 + i,
            "ok": 8 + i,
            "failed": 2,
            "detail": detail or f"considered={10 + i} ok={8 + i} failed=2",
        })
    return {
        "generated_at": "2026-05-30T12:00:00+00:00",
        "filters": {
            "limit": 5000,
            "provider": "canvas",
            "action": "",
            "since": "2026-05-01T00:00:00+00:00",
            "before": "2026-05-30T23:59:59+00:00",
        },
        "alarms": [],
        "rollup_by_action": {},
        "rollup_by_provider": {},
        "retention_counters": {},
        "entry_count": n_entries,
        "entries": entries,
    }


def main() -> int:
    print("=== v4.00.87 T2+T3 — audit_packet jsonl + hmac smoke ===")

    # ----- T2: JSONL streaming export -----
    print("\n-- T2 JSONL --")

    # Case 1: build fake packet w/ 3 entries.
    packet = _fake_packet(n_entries=3)
    _check("01 fake packet built (3 entries)",
           len(packet.get("entries") or []) == 3,
           f"entries={len(packet['entries'])}")

    # Case 2: render returns bytes.
    out = render_audit_packet_jsonl(packet)
    _check("02 render_audit_packet_jsonl returns bytes",
           isinstance(out, (bytes, bytearray)),
           f"type={type(out).__name__} len={len(out)}")

    # Case 3: gzip magic.
    _check("03 starts w/ gzip magic",
           bytes(out[:2]) == b"\x1f\x8b",
           f"head={out[:2]!r}")

    # Case 4: decode returns list w/ 4 items (envelope + 3 entries).
    decoded = decode_audit_packet_jsonl(out)
    _check("04 decode returns list of 4 (envelope + 3 entries)",
           isinstance(decoded, list) and len(decoded) == 4,
           f"type={type(decoded).__name__} len={len(decoded)}")

    # Case 5: first item is the envelope.
    first = decoded[0] if decoded else {}
    _check("05 first item has _envelope=True",
           bool(first.get("_envelope")) is True,
           f"first_keys={sorted(first.keys()) if isinstance(first, dict) else type(first).__name__}")

    # Case 6: subsequent items are entries (have action/provider, no _envelope).
    rest_ok = True
    rest_notes = []
    for i, rec in enumerate(decoded[1:], start=1):
        if not isinstance(rec, dict):
            rest_ok = False
            rest_notes.append(f"idx{i}=not_dict")
            continue
        if rec.get("_envelope"):
            rest_ok = False
            rest_notes.append(f"idx{i}=has_envelope")
        if "action" not in rec or "provider" not in rec:
            rest_ok = False
            rest_notes.append(f"idx{i}=missing_action_or_provider")
    _check("06 subsequent items have action/provider (no _envelope)",
           rest_ok,
           "; ".join(rest_notes) if rest_notes else "all 3 entries clean")

    # Case 7: determinism — two calls -> same bytes.
    again = render_audit_packet_jsonl(packet)
    _check("07 deterministic across calls",
           out == again,
           f"a_len={len(out)} b_len={len(again)} eq={out == again}")

    # Case 8: detail truncation at 1024 chars.
    big_packet = _fake_packet(n_entries=1, detail="X" * 4096)
    big_decoded = decode_audit_packet_jsonl(render_audit_packet_jsonl(big_packet))
    big_entry = big_decoded[1] if len(big_decoded) > 1 else {}
    big_detail = big_entry.get("detail", "") if isinstance(big_entry, dict) else ""
    _check("08 detail truncated to 1024 chars",
           len(big_detail) == 1024,
           f"got_len={len(big_detail)} expected=1024")

    # Case 9: empty packet -> still emits envelope w/ row_count=0.
    empty_out = render_audit_packet_jsonl({})
    empty_decoded = decode_audit_packet_jsonl(empty_out)
    _check("09a empty packet decoded as list of 1 (envelope only)",
           isinstance(empty_decoded, list) and len(empty_decoded) == 1,
           f"len={len(empty_decoded)}")
    env = empty_decoded[0] if empty_decoded else {}
    _check("09b envelope has row_count=0",
           isinstance(env, dict) and env.get("_envelope") is True
           and env.get("row_count") == 0,
           f"envelope={env!r}")

    # ----- T3: HMAC signature with tenant-isolated salt -----
    print("\n-- T3 HMAC --")

    # Case 10: signature is 64-char hex.
    sig_acme = sign_audit_packet(packet, tenant_schema="acme")
    _check("10 sign_audit_packet returns 64-char hex",
           isinstance(sig_acme, str) and len(sig_acme) == 64
           and all(c in "0123456789abcdef" for c in sig_acme),
           f"len={len(sig_acme)} sig={sig_acme[:16]}…")

    # Case 11: deterministic — same inputs -> same hex.
    sig_acme_again = sign_audit_packet(packet, tenant_schema="acme")
    _check("11 deterministic same-input signature",
           sig_acme == sig_acme_again,
           f"eq={sig_acme == sig_acme_again}")

    # Case 12: different tenant_schema -> different hex (tenant isolation).
    sig_globex = sign_audit_packet(packet, tenant_schema="globex")
    _check("12 different tenant_schema -> different signature",
           sig_acme != sig_globex,
           f"acme[:16]={sig_acme[:16]} globex[:16]={sig_globex[:16]}")

    # Case 13: verify correct signature returns {ok: True}.
    v_ok = verify_audit_packet_signature(packet,
                                          tenant_schema="acme",
                                          expected_signature=sig_acme)
    _check("13 verify correct sig returns ok=True",
           isinstance(v_ok, dict) and v_ok.get("ok") is True
           and v_ok.get("computed") == sig_acme,
           f"v={v_ok!r}")

    # Case 14: wrong signature -> {ok: False, computed: <hex>}.
    v_bad = verify_audit_packet_signature(packet,
                                           tenant_schema="acme",
                                           expected_signature="00" * 32)
    _check("14 wrong signature -> ok=False with computed hex",
           isinstance(v_bad, dict) and v_bad.get("ok") is False
           and isinstance(v_bad.get("computed"), str)
           and len(v_bad.get("computed", "")) == 64,
           f"v={v_bad!r}")

    # Case 15: wrong tenant -> ok=False (verify under globex against acme sig).
    v_wrong_tenant = verify_audit_packet_signature(packet,
                                                    tenant_schema="globex",
                                                    expected_signature=sig_acme)
    _check("15 wrong tenant -> ok=False",
           isinstance(v_wrong_tenant, dict)
           and v_wrong_tenant.get("ok") is False,
           f"v={v_wrong_tenant!r}")

    # Case 16: mutating the packet -> different signature (tamper detection).
    mutated = _fake_packet(n_entries=3)
    mutated["entries"][0]["ok"] = 999  # mutation
    sig_mutated = sign_audit_packet(mutated, tenant_schema="acme")
    _check("16 mutated packet -> different signature (tamper detection)",
           sig_mutated != sig_acme,
           f"original[:16]={sig_acme[:16]} mutated[:16]={sig_mutated[:16]}")

    # Case 17: PII guard — the dev-fallback constant must NEVER appear in any
    # production-style output we generated. (smoke-only — we just confirm
    # the constant does not leak into the JSONL/CSV/signature surfaces.)
    sentinel = _DEFAULT_ROOT_FOR_TEST
    csv_text = decode_audit_packet_csv(render_audit_packet_csv(packet))
    jsonl_text = ""
    try:
        import gzip as _gz
        jsonl_text = _gz.decompress(out).decode("utf-8")
    except Exception:  # noqa: BLE001
        jsonl_text = ""
    leak_corpus = csv_text + jsonl_text + sig_acme + sig_globex
    _check("17 dev-fallback root NEVER appears in CSV/JSONL/signature output",
           sentinel not in leak_corpus,
           f"sentinel_len={len(sentinel)} leak={'YES' if sentinel in leak_corpus else 'no'}")

    # ----- Regression: Wave 18 T5 CSV exporter still works. -----
    print("\n-- Regression: v4.00.86 T5 CSV --")
    reg_csv = render_audit_packet_csv(packet)
    reg_text = decode_audit_packet_csv(reg_csv)
    expected_header = ("created_at_iso,action,provider,actor_hash,"
                       "considered,ok_count,failed_count,detail")
    _check("R1 CSV gzip magic", bytes(reg_csv[:2]) == b"\x1f\x8b",
           f"head={reg_csv[:2]!r}")
    _check("R2 CSV header present", expected_header in reg_text,
           f"present={'yes' if expected_header in reg_text else 'no'}")
    _check("R3 CSV starts w/ #packet_generated_at,",
           reg_text.startswith("#packet_generated_at,"),
           f"head={reg_text[:48]!r}")

    # Tally.
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    total = len(_RESULTS)
    print()
    print(f"=== RESULT: {passed}/{total} cases green ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
