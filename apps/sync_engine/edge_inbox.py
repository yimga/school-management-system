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
from apps.sync_engine.tombstones import DELETE_OP


def split_bundle_rows(rows):
    """Split bundle rows into ``(updates, inserts, deletes, malformed)``.

    Shared by BOTH receivers (the box's pull inbox and the cloud's upload view) so the
    two can never disagree about what a row is. They previously each open-coded a
    two-way split, which is exactly how a third row kind - the deletion - could be added
    to the wire and be silently applied as an UPDATE-with-no-fields on one side.

    A signed bundle line is raw ``json.loads`` output, so a scalar or array line would
    ``AttributeError`` on ``.get(...)``; those are counted as malformed rather than
    allowed to take down the batch.
    """
    updates, inserts, deletes, malformed = [], [], [], 0
    for row in rows:
        if not isinstance(row, dict):
            malformed += 1
            continue
        if str(row.get("op") or "").strip().lower() == DELETE_OP:
            deletes.append(row)
        elif (row.get("client_offline_id") or "").strip():
            inserts.append(row)
        else:
            updates.append(row)
    return updates, inserts, deletes, malformed


def tally_skipped_rows(
    update_results, insert_results, delete_results, *, conflict_indexes=frozenset()
):
    """Count rows the far side sent that this side could NOT apply, keyed by reason.

    A row that was neither applied nor raised as a conflict is SKIPPED, and it used to be
    invisible: the caller saw "received N" and reported that as moved, so a bundle in which
    every row was refused still read as a clean sync.

    Shared by BOTH receivers - the box's pull inbox and the cloud's upload view - for the
    same reason :func:`split_bundle_rows` is: the pull side learned to count refusals and
    the push side did not, so the identical 409 was a named reason coming down and silence
    going up. One implementation is what stops the two from drifting apart again.

    Returns ``(skipped_reasons, missing_parents)``.

    ``missing_parents`` records WHICH parent, not just how many. A `missing_reference` used
    to arrive at the runner as a bare count, and the runner's only healing move - rewinding
    the pull cursor for a full-corpus replay - is worth making ONLY when the absent parent
    is a row the rail can actually deliver. A parent whose table does not ride will not
    appear in a replay, in this replay or any future one, so on that evidence the rewind is
    a guaranteed-futile re-download of the entire corpus, every cooldown, forever. Keeping
    the model label here is what lets the runner tell the two cases apart.

    ``conflict_indexes`` applies to ``update_results`` ONLY. The three result lists index
    INDEPENDENTLY (each enumerates its own row list), and conflicts only ever come from
    ``apply_changes``, so matching those indexes against the insert or delete results would
    silently drop unrelated refusals that happen to share an index.
    """
    skipped_reasons: dict = {}
    missing_parents: dict = {}

    def _tally(results, indexes=frozenset()):
        for res in results or ():
            if res.get("status") in (200, 201):
                continue
            # A CONFLICT is not a skip: it has its own surface and its own operator
            # workflow, and counting it twice would inflate the number whose whole meaning
            # is "nobody is looking at this".
            if res.get("index") in indexes:
                continue
            data = res.get("data") or {}
            reason = str(data.get("error") or "unknown")
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
            if reason == "missing_reference":
                label = str(data.get("references") or "").strip()
                if label:
                    missing_parents[label] = missing_parents.get(label, 0) + 1

    _tally(update_results, conflict_indexes)
    _tally(insert_results)
    _tally(delete_results)
    return skipped_reasons, missing_parents


def apply_pulled_bundle(school, user, body_bytes: bytes, *, origin: str = "cloud-pull") -> dict:
    """Verify a pulled bundle for ``school`` and apply its rows on the box.

    Splits cloned-record UPDATES (by pk — the clone is pk-preserving) from
    offline-CREATED rows (carry a ``client_offline_id``; upserted by
    ``(school, client_offline_id)``), exactly like the upload receiver. ``origin`` is
    stamped as the sync provenance so the reverse push won't echo these rows.

    Returns a result dict; ``{"ok": False, "errors": [...]}`` if the signature / school
    binding fails (nothing is applied).
    """
    try:
        return _apply_pulled_bundle_inner(school, user, body_bytes, origin=origin)
    except Exception as exc:  # noqa: BLE001 — never abort the sync runner mid-cycle
        return {"ok": False, "errors": [str(exc)[:500]]}


def _apply_pulled_bundle_inner(school, user, body_bytes: bytes, *, origin: str = "cloud-pull") -> dict:
    from apps.api.sync_services import (
        _get_entity_config,
        _insert_dependency_order,
        apply_changes,
        apply_deletes,
        apply_edge_inserts,
    )

    collected: dict = {}
    rows, errors = verify_and_parse_bundle(
        body_bytes, expected_school_id=school.pk, collect=collected
    )
    if errors:
        return {"ok": False, "errors": errors}

    # Replay defence applies in BOTH directions. The cloud->box leg is the one where a
    # replay is most damaging, because the box treats a pulled bundle as authoritative:
    # re-presenting a bundle captured before a deletion resurrects the row.
    from apps.sync_engine.replay_guard import register_bundle

    replay = register_bundle(school, collected, direction=origin, row_count=len(rows))
    if replay:
        return {"ok": False, "errors": [replay]}

    update_rows, insert_rows, delete_rows, malformed = split_bundle_rows(rows)

    config = _get_entity_config(include_derived=True)
    dep_order = _insert_dependency_order(config)

    def _dep_rank(row):
        et = (row.get("entity_type") or "").strip().lower()
        return dep_order.index(et) if et in dep_order else len(dep_order)

    update_rows.sort(key=_dep_rank)
    insert_rows.sort(key=_dep_rank)

    out = apply_changes(
        str(school.id), user, update_rows, persist_conflicts=True, sync_origin=origin
    )
    inserted = (
        apply_edge_inserts(str(school.id), user, insert_rows, sync_origin=origin)
        if insert_rows
        else {"created": 0, "updated": 0, "results": []}
    )
    # Deletions apply LAST. A bundle can legitimately carry an update AND a later deletion
    # of the same row (two changes, one window); applying the deletion last is what makes
    # the end state match the far side's rather than depending on wire order.
    removed = (
        apply_deletes(str(school.id), user, delete_rows, sync_origin=origin)
        if delete_rows
        else {"deleted": 0, "results": []}
    )
    # A row that was neither applied nor raised as a conflict is SKIPPED, and until now it
    # was invisible: the caller saw "received N" and reported that as pulled, so a bundle
    # in which every row was refused still read as a clean sync. Count them and keep the
    # reasons, so "sync is green" cannot mean "nothing landed".
    skipped_reasons, missing_parents = tally_skipped_rows(
        out["results"],
        inserted["results"],
        removed["results"],
        conflict_indexes={c.get("index") for c in out["conflicts"]},
    )

    return {
        "ok": True,
        "received": len(rows),
        "malformed": malformed,
        "applied": out["success_count"],
        "conflicts": len(out["conflicts"]),
        "created": inserted["created"],
        "upserted": inserted["updated"],
        "deleted": removed["deleted"],
        "skipped": sum(skipped_reasons.values()),
        "skipped_reasons": skipped_reasons,
        "skipped_missing_parents": missing_parents,
        "conflict_details": out["conflicts"],
        "results": out["results"],
        "insert_results": inserted["results"],
        "delete_results": removed["results"],
    }


__all__ = ["apply_pulled_bundle", "split_bundle_rows", "tally_skipped_rows"]
