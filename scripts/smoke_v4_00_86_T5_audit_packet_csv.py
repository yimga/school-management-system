"""v4.00.86 Wave 18 Target 5 smoke — audit-packet CSV export.

Validates :func:`apps.migration_cloud.audit_packet_csv.render_audit_packet_csv`
and its decoder. No DB required — we hand-build a fake packet dict.
"""
from __future__ import annotations

import os
import sys


# Ensure repo root is on sys.path so ``apps.*`` imports resolve when the
# script is run directly (e.g. ``python scripts/smoke_v4_00_86_T5_audit_packet_csv.py``).
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


from apps.migration_cloud.audit_packet_csv import (  # noqa: E402
    render_audit_packet_csv,
    decode_audit_packet_csv,
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
    print("=== v4.00.86 T5 — audit_packet_csv smoke ===")

    # Case 1: build a fake packet dict w/ 3 entries.
    packet = _fake_packet(n_entries=3)
    _check("01 fake packet built", len(packet.get("entries") or []) == 3,
           f"entries={len(packet['entries'])}")

    # Case 2: render returns bytes.
    out = render_audit_packet_csv(packet)
    _check("02 render returns bytes", isinstance(out, (bytes, bytearray)),
           f"type={type(out).__name__} len={len(out)}")

    # Case 3: gzip magic.
    _check("03 starts w/ gzip magic", bytes(out[:2]) == b"\x1f\x8b",
           f"head={out[:2]!r}")

    # Case 4: decode returns str.
    text = decode_audit_packet_csv(out)
    _check("04 decode returns str", isinstance(text, str),
           f"type={type(text).__name__} len={len(text)}")

    # Case 5: starts with #packet_generated_at,
    _check("05 starts w/ #packet_generated_at,",
           text.startswith("#packet_generated_at,"),
           f"head={text[:64]!r}")

    # Case 6: 8-column header row present.
    expected_header = ("created_at_iso,action,provider,actor_hash,"
                       "considered,ok_count,failed_count,detail")
    _check("06 includes 8-col header row", expected_header in text,
           f"expected={expected_header!r} present={'yes' if expected_header in text else 'no'}")

    # Case 7: 3 data rows present (count lines AFTER header).
    lines = text.split("\n")
    header_idx = None
    for i, ln in enumerate(lines):
        if ln == expected_header:
            header_idx = i
            break
    data_rows = []
    if header_idx is not None:
        for ln in lines[header_idx + 1:]:
            if ln.strip():
                data_rows.append(ln)
    _check("07 has exactly 3 data rows", len(data_rows) == 3,
           f"got={len(data_rows)}")

    # Case 8: empty packet -> gzipped CSV w/ row_count=0.
    empty_out = render_audit_packet_csv({"entries": []})
    _check("08a empty render gzip magic", bytes(empty_out[:2]) == b"\x1f\x8b",
           f"head={empty_out[:2]!r}")
    empty_text = decode_audit_packet_csv(empty_out)
    _check("08b empty row_count=0 in header", "#row_count,0" in empty_text,
           f"present={'yes' if '#row_count,0' in empty_text else 'no'}")
    # And the column header still rendered.
    _check("08c empty includes header row", expected_header in empty_text)

    # Case 9: determinism — two calls -> identical bytes.
    again = render_audit_packet_csv(packet)
    _check("09 deterministic across calls", out == again,
           f"a_len={len(out)} b_len={len(again)} eq={out == again}")

    # Case 10: detail truncation.
    big_packet = _fake_packet(n_entries=1, detail="X" * 1024)
    big_text = decode_audit_packet_csv(render_audit_packet_csv(big_packet))
    # Pull the last non-empty line (the single data row) and inspect its detail cell.
    big_lines = [ln for ln in big_text.split("\n") if ln.strip()]
    last = big_lines[-1] if big_lines else ""
    # csv module quotes when needed; our detail is just "X"*1024 (no
    # commas/quotes) so it'll be unquoted. The detail cell is the trailing
    # column.
    parts = last.rsplit(",", 1)
    detail_cell = parts[-1] if parts else ""
    _check("10 detail cell <= 512 chars",
           len(detail_cell) <= 512,
           f"len={len(detail_cell)}")
    _check("10b detail truncation is the cap",
           len(detail_cell) == 512,
           f"got_len={len(detail_cell)} expected=512")

    # Case 11: no secret-substring leaks.
    forbidden = ("client_secret", "private_key", "api_key")
    leak_text = text + empty_text + big_text
    leaks = [s for s in forbidden if s in leak_text]
    _check("11 no client_secret/private_key/api_key substrings",
           not leaks,
           f"leaks={leaks}")

    # Tally.
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    total = len(_RESULTS)
    print()
    print(f"=== RESULT: {passed}/{total} cases green ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
