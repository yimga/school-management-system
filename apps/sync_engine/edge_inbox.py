"""Edge inbox — verify + apply a delta bundle PULLED down from the operator.

The box-side counterpart to :mod:`apps.sync_engine.edge_outbox`. The operator serves a
signed delta bundle via the download endpoint; this module verifies it and routes the
rows through the SAME apply path the upload receiver uses (``apply_changes`` /
``apply_edge_inserts``), stamping ``sync_origin`` so the echo-suppression ledger keeps
the box from pushing the just-pulled rows straight back up.

Cloud->box is edge-INITIATED (the box calls out and applies what it gets), so nothing
here opens an inbound port on the box.
"""
from __future__ import annotations

from apps.sync_engine.delta_bundle import verify_and_parse_bundle


def apply_pulled_bundle(school, user, body_bytes: bytes, *, origin: str = "cloud-pull") -> dict:
    """Verify a pulled bundle for ``school`` and apply its rows on the box.

    Splits cloned-record UPDATES (by pk — the clone is pk-preserving) from
    offline-CREATED rows (carry a ``client_offline_id``; upserted by
    ``(school, client_offline_id)``), exactly like the upload receiver. ``origin`` is
    stamped as the sync provenance so the reverse push won't echo these rows.

    Returns a result dict; ``{"ok": False, "errors": [...]}`` if the signature / school
    binding fails (nothing is applied).
    """
    from apps.api.sync_services import apply_changes, apply_edge_inserts

    rows, errors = verify_and_parse_bundle(body_bytes, expected_school_id=school.pk)
    if errors:
        return {"ok": False, "errors": errors}

    update_rows, insert_rows, malformed = [], [], 0
    for row in rows:
        if not isinstance(row, dict):
            malformed += 1
            continue
        (insert_rows if (row.get("client_offline_id") or "").strip() else update_rows).append(row)

    out = apply_changes(
        str(school.id), user, update_rows, persist_conflicts=True, sync_origin=origin
    )
    inserted = (
        apply_edge_inserts(str(school.id), user, insert_rows, sync_origin=origin)
        if insert_rows
        else {"created": 0, "updated": 0, "results": []}
    )
    return {
        "ok": True,
        "received": len(rows),
        "malformed": malformed,
        "applied": out["success_count"],
        "conflicts": len(out["conflicts"]),
        "created": inserted["created"],
        "upserted": inserted["updated"],
        "conflict_details": out["conflicts"],
        "results": out["results"],
        "insert_results": inserted["results"],
    }


__all__ = ["apply_pulled_bundle"]
