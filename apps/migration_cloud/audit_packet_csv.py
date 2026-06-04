# v4.00.86 — CSV export companion to build_audit_row_export_packet.
#
# Counsel-handoff PDF generation often wants tabular CSV for spreadsheet
# ingestion. Deterministic, gzipped, mtime=0 stable.
#
# The CSV format:
#   1. A leading block of ``#``-prefixed metadata rows (packet generated_at,
#      filter window provider/action/since/before, row_count). These mirror
#      the v4.00.68 retention-preview CSV ``#summary`` convention so the
#      counsel spreadsheet can pivot on the same comment markers.
#   2. A blank row separator.
#   3. An 8-column header row.
#   4. One row per ``entries[i]`` event.
#
# The ``entries[]`` shape comes from ``_row_to_action_event`` /
# ``_diag_row_to_event`` in views_lms_diagnostics.py — keys: ``ts_iso``,
# ``actor_hash``, ``action``, ``provider``, ``considered``, ``ok``,
# ``failed``. We surface those (renaming ``ts_iso`` -> ``created_at_iso``
# in the CSV header for human friendliness) plus a ``detail`` column for
# when the upstream snapshot includes it. Detail is hard-capped at 512
# chars to keep counsel spreadsheets from blowing up on giant payloads.
#
# Secret-leak defense: this exporter NEVER reaches into the event dict for
# any field other than the 7 declared columns + ``detail``, so client
# secrets / private keys / api keys cannot enter the CSV by accident.

import csv
import gzip
import io


_AUDIT_PACKET_CSV_COLUMNS = (
    "created_at_iso", "action", "provider", "actor_hash",
    "considered", "ok_count", "failed_count", "detail",
)

_AUDIT_PACKET_CSV_DETAIL_CAP = 512


def render_audit_packet_csv(packet: dict) -> bytes:
    """Return the packet's ``entries`` array as gzipped CSV.

    Headers carry packet-level metadata in commented rows (``#``-prefixed)
    so a counsel spreadsheet can pivot on the window. Determinism: rows in
    input order; gzip mtime=0 so two calls on the same packet produce
    identical bytes. NEVER raises (best-effort: missing fields render as
    empty cells).
    """
    if not isinstance(packet, dict):
        packet = {}
    entries = packet.get("entries", []) or []
    filters = packet.get("filters") or {}

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["#packet_generated_at", str(packet.get("generated_at", ""))])
    writer.writerow(["#packet_window_provider", str(filters.get("provider", ""))])
    writer.writerow(["#packet_window_action", str(filters.get("action", ""))])
    writer.writerow(["#packet_window_since", str(filters.get("since", ""))])
    writer.writerow(["#packet_window_before", str(filters.get("before", ""))])
    writer.writerow(["#row_count", str(len(entries))])
    writer.writerow([])
    writer.writerow(list(_AUDIT_PACKET_CSV_COLUMNS))
    for row in entries:
        if not isinstance(row, dict):
            continue
        # ``ts_iso`` is the ring-buffer / DB-projection field name in
        # _row_to_action_event / _diag_row_to_event. ``created_at_iso``
        # is its CSV-friendly alias. Accept either for robustness.
        created_at = row.get("created_at_iso", "") or row.get("ts_iso", "")
        detail_raw = row.get("detail", "") or ""
        detail = str(detail_raw)[:_AUDIT_PACKET_CSV_DETAIL_CAP]
        writer.writerow([
            str(created_at),
            str(row.get("action", "")),
            str(row.get("provider", "")),
            str(row.get("actor_hash", "")),
            str(row.get("considered", "")),
            # Counter column names in the entries use the short form
            # (``ok`` / ``failed``); CSV header uses the audit-DB column
            # names (``ok_count`` / ``failed_count``) so counsel can join
            # against the canonical LMSDiagActionAudit schema.
            str(row.get("ok_count", row.get("ok", ""))),
            str(row.get("failed_count", row.get("failed", ""))),
            detail,
        ])

    csv_bytes = buf.getvalue().encode("utf-8")
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
        gz.write(csv_bytes)
    return out.getvalue()


def decode_audit_packet_csv(blob: bytes) -> str:
    """Inverse of :func:`render_audit_packet_csv` — returns the CSV text."""
    return gzip.decompress(blob).decode("utf-8")


# v4.00.87 — JSONL (newline-delimited JSON) streaming export.
#
# Each line is a JSON object — easier to stream into log aggregators
# (Splunk, Datadog) than CSV. First line is the packet metadata
# envelope; subsequent lines are entries one per row.

import json


def render_audit_packet_jsonl(packet: dict) -> bytes:
    """Return packet entries as gzipped JSONL bytes.
    First line: {"_envelope": True, "generated_at": ..., "filters": {...}, "row_count": N}
    Subsequent lines: one JSON object per entry."""
    entries = packet.get("entries", []) or []
    lines: list[str] = []
    envelope = {
        "_envelope": True,
        "generated_at": packet.get("generated_at", ""),
        "filters": packet.get("filters", {}),
        "row_count": len(entries),
    }
    lines.append(json.dumps(envelope, sort_keys=True, separators=(",", ":")))
    for row in entries:
        # Truncate detail to 1024 chars
        out_row = dict(row)
        detail = out_row.get("detail", "")
        if detail and len(detail) > 1024:  # magic-number-allow: field-char-cap
            out_row["detail"] = detail[:1024]  # magic-number-allow: string-truncation-cap
        lines.append(json.dumps(out_row, sort_keys=True, separators=(",", ":"), default=str))
    text = "\n".join(lines) + "\n"
    out_buf = io.BytesIO()
    with gzip.GzipFile(fileobj=out_buf, mode="wb", mtime=0) as gz:
        gz.write(text.encode("utf-8"))
    return out_buf.getvalue()


def decode_audit_packet_jsonl(blob: bytes) -> list[dict]:
    """Return the parsed JSONL records list (envelope first)."""
    text = gzip.decompress(blob).decode("utf-8")
    return [json.loads(line) for line in text.split("\n") if line.strip()]


# v4.00.87 — Tenant-isolated HMAC signature for tamper-evident packets.
#
# When counsel receives a packet, they need to verify it came from the
# tenant that says it did. HMAC-SHA256 keyed by tenant-isolated derived
# secret. The "tenant-isolated" part means we derive per-tenant keys
# from a platform root + tenant_schema so one tenant's leaked key can't
# forge another tenant's packets.

import hmac
import hashlib
import os


_PLATFORM_ROOT_ENV = "RMC_AUDIT_PACKET_SIGNING_ROOT"
_DEFAULT_ROOT_FOR_TEST = "v4-00-87-default-fallback-root-DO-NOT-USE-IN-PROD"


def _derive_tenant_hmac_key(*, tenant_schema: str) -> bytes:
    """HKDF-lite: HMAC(root, tenant_schema) -> per-tenant key bytes."""
    root = os.environ.get(_PLATFORM_ROOT_ENV, _DEFAULT_ROOT_FOR_TEST)
    return hmac.new(
        root.encode("utf-8"),
        f"tenant:{tenant_schema or ''}".encode("utf-8"),
        hashlib.sha256,
    ).digest()


def sign_audit_packet(packet: dict, *, tenant_schema: str) -> str:
    """Return hex HMAC-SHA256 over canonical JSON of packet, using
    per-tenant derived key."""
    canonical = json.dumps(packet, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    key = _derive_tenant_hmac_key(tenant_schema=tenant_schema)
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def verify_audit_packet_signature(packet: dict, *, tenant_schema: str, expected_signature: str) -> dict:
    """Constant-time signature verification. Returns
    {"ok": bool, "computed": "<hex>"}. Never raises."""
    try:
        computed = sign_audit_packet(packet, tenant_schema=tenant_schema)
        ok = hmac.compare_digest(computed, str(expected_signature or ""))
        return {"ok": ok, "computed": computed}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "computed": "", "error": type(exc).__name__}
