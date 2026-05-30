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
