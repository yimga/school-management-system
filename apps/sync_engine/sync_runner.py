"""Self-healing edge<->cloud sync runner for the Sync Center "Sync now" button.

A thin, NEVER-RAISING wrapper over the SAME edge services the scheduled
``edge_sync_cycle`` command drives:

  * PUSH — ``edge_outbox.build_edge_delta_bundle`` + ``edge_outbox.post_bundle``
  * PULL — ``edge_outbox.pull_bundle`` + ``edge_inbox.apply_pulled_bundle``

Whatever happens — the flag is off, the operator is unreachable, a bundle is rejected —
:func:`run_sync_cycle` returns a result dict AND records EXACTLY ONE
:class:`~apps.sync_engine.models.EdgeSyncRun`, so a tenant-admin click shows an outcome
instead of crashing the page. Each direction is wrapped independently (mirroring
``edge_sync_cycle``'s resilience) so a failing push never aborts the pull, and vice versa.

GATED by ``settings.RMC_EDGE_SYNC_ENABLED`` exactly like the command: off => no network,
a recorded ok=False "not enabled" row, and a clean ``{"enabled": False, ...}`` return.

Money stays cloud-authoritative — this only drives the existing protocol and changes no
conflict/money policy.

    mode="live"  push local changes UP, then pull cloud changes DOWN and apply them.
    mode="dry"   NO-WRITE CHECK: builds the local delta only to preview the pending count
                 (never POSTs it) and fetches the cloud download endpoint only to confirm
                 reachability + that the credential is accepted (never applies the bundle).
                 Nothing is written in EITHER direction — this is the safe connectivity
                 probe the pre-offline sync gate runs before a box may go dark.
"""
from __future__ import annotations

import logging

from django.conf import settings
from apps.sync_engine.cloud_endpoints import cloud_endpoint
from django.utils import timezone

logger = logging.getLogger(__name__)

# How long to wait before requesting ANOTHER full replay for the same school. A replay is
# expensive, and a reference a replay cannot satisfy (a parent belonging to another tenant,
# a parent genuinely deleted upstream) would otherwise rewind the cursor on every cycle
# forever. One rewind per window; the decision is reported either way.
_MISSING_REF_REPLAY_COOLDOWN_SECONDS = 6 * 3600  # magic-number-allow: replay cooldown (6h, seconds)
_MISSING_REF_REPLAY_KEY = "rmc:edge_sync:missing_ref_replay:%s"


def _request_replay_for_missing_parents(school) -> str:
    """Rewind the PULL cursor so the next cycle replays the whole corpus.

    A ``missing_reference`` means the bundle carried a CHILD whose PARENT this box does not
    have. The parent is absent from the delta because its own ``updated_at`` is older than
    the pull cursor, so an incremental delta will never offer it again — the child would be
    refused on every future cycle and the two sides would stay silently divergent. Rewinding
    to "no position" makes the next cycle request the corpus from the beginning, which DOES
    contain the parent; the cloud-authored create path lands it, and the child follows.

    Returns the note to show the operator. Never raises: a healing step must not be the
    thing that breaks a sync cycle.
    """
    from django.core.cache import cache

    from apps.sync_engine.models import EdgeSyncCursor, reset_sync_cursors

    try:
        key = _MISSING_REF_REPLAY_KEY % school.pk
        # cache.add only succeeds when the key is absent, so the cooldown is atomic even if
        # two cycles overlap.
        if not cache.add(key, 1, _MISSING_REF_REPLAY_COOLDOWN_SECONDS):
            return (
                "records are still waiting on a parent this box has not received; a full "
                "replay was requested recently, so this cycle did not request another"
            )
        reset_sync_cursors(school, direction=EdgeSyncCursor.PULL)
        return (
            "records referenced a parent this box does not have; rewound the pull cursor "
            "so the next cycle replays the full corpus and collects the missing parents"
        )
    except Exception as exc:  # noqa: BLE001 - healing must never break the cycle
        logger.debug("replay request for missing parents failed", exc_info=True)
        return f"could not request a replay for the missing parents: {exc}"


def _flush_drifted_entities(school, endpoint, token, user, drifted) -> str:
    """G8 repair: re-pull the drifted entities WHOLE, one entity at a time.

    Targeted on purpose. The cursor is per ``(school, direction)``, so the existing
    healing move — rewinding it — replays the ENTIRE corpus to repair one table, which on
    a metered link is a bill and on a large school is an hour. Parity already knows which
    entity is wrong, so the repair asks for exactly that one with ``since=None`` and
    leaves the cursor alone: nothing else re-ships, and the pull cursor keeps meaning what
    it meant before this ran.

    Rides the ordinary rail end to end — the same download endpoint, the same signature,
    the same idempotent apply — so a row that was merely stale is overwritten by the same
    conflict policy as any other pull, a row that was missing is created by the ordinary
    cloud-pull create path, and a row this side must not lose is protected by exactly the
    guards that protect it on every other cycle. It is a normal pull with a narrow scope,
    not a privileged repair channel.

    ONE ENTITY PER REQUEST rather than one request for all of them, for PARTIAL PROGRESS.
    (Not for the row cap — ``RMC_SYNC_BUNDLE_MAX_ROWS`` is enforced on the UPLOAD receiver
    in ``sync_bundle_api``, and the pull side applies whatever it is handed; the existing
    full-resync path relies on exactly that.) The reason is that a repair runs on the link
    that was already unreliable enough to lose rows: batching three full entities into one
    request means a drop at 90% repairs nothing, while three requests mean the first two
    landed and the third is named as still drifted. It also keeps one entity's failure —
    a missing reference, a policy refusal — from being reported as all three failing.

    Returns the operator note. Never raises: a repair must not be the thing that breaks
    the cycle it is repairing.
    """
    try:
        from apps.sync_engine import edge_outbox, parity
        from apps.sync_engine.edge_inbox import apply_pulled_bundle

        cap = parity.max_flush_entities()
        targets = list(drifted)[:cap]
    except Exception as exc:  # noqa: BLE001 - the setup must be as safe as the loop
        # The per-entity loop below is individually guarded, but the setup was not: an
        # import that fails here would raise out of a repair whose whole contract is that
        # it cannot break the cycle it is repairing — and it would surface as "pull
        # failed" AFTER the pull had already succeeded and advanced the cursor.
        logger.debug("parity flush could not start", exc_info=True)
        return f"parity flush could not start: {exc}"
    if not targets:
        return ""
    repaired, failed = [], []
    for entity_type in targets:
        try:
            status, body, _hw = edge_outbox.pull_bundle(
                endpoint, token, since=None, entities=[entity_type]
            )
            if status != 200:
                failed.append(f"{entity_type} (HTTP {status})")
                continue
            applied = apply_pulled_bundle(school, user, body, origin="cloud-pull")
            if not applied.get("ok"):
                failed.append(f"{entity_type} ({applied.get('errors')})")
                continue
            repaired.append(
                f"{entity_type} ({int(applied.get('created') or 0)} created, "
                f"{int(applied.get('upserted') or 0)} updated)"
            )
        except Exception as exc:  # noqa: BLE001 - one bad entity must not stop the rest
            logger.debug("parity flush failed for %s", entity_type, exc_info=True)
            failed.append(f"{entity_type} ({exc})")

    bits = []
    if repaired:
        bits.append("parity flush repaired " + ", ".join(repaired))
    if failed:
        bits.append("parity flush could NOT repair " + ", ".join(failed))
    if len(drifted) > cap:
        # Named, never silent. A capped repair that reports only what it fixed reads as
        # "everything is fixed now", and the operator stops looking.
        deferred = ", ".join(list(drifted)[cap:])
        bits.append(
            f"{len(drifted) - cap} more entit(ies) still drifted and NOT repaired this "
            f"cycle ({deferred}); they follow on later cycles"
        )
    return "; ".join(bits)


def _operator_base() -> str:
    """Operator (cloud) base URL the box pushes/pulls against.

    Resolved by ``edge_binding``: the durable pairing binding first, then the
    environment for boxes that were never paired, then derived from the school slug.
    Empty is tolerated — the transport call simply fails and is recorded.
    """
    from apps.sync_engine.edge_binding import operator_base

    return operator_base()


def _edge_token() -> str:
    """Edge machine credential, from the pairing binding or the legacy env var."""
    from apps.sync_engine.edge_binding import edge_credential

    return edge_credential()


def _endpoint(base: str, url_name: str) -> str:
    """Absolute url on the cloud. Fallback paths live in cloud_endpoints.

    The literal used to be passed in per call site, and both of this module's
    were wrong (``/api/v1/sync/...``, a prefix carrying no sync routes), so a
    box that could not reverse asked the cloud for a nonexistent path and got
    the tenant HTML catch-all back as a 404.
    """
    return cloud_endpoint(base, url_name)


def _page_size() -> int:
    """Rows per pushed bundle — the receiver's own cap, which it rejects ABOVE, whole.

    Defaults to the same 500 ``SyncBundleUploadView`` uses. Floored at 1 so a
    misconfigured 0 cannot produce an infinite loop of empty pages.
    """
    # magic-number-allow: mirrors SyncBundleUploadView's own RMC_SYNC_BUNDLE_MAX_ROWS default
    default_cap = 500
    return max(1, int(getattr(settings, "RMC_SYNC_BUNDLE_MAX_ROWS", default_cap) or default_cap))


def _max_pages_per_cycle() -> int:
    """Ceiling on bundles POSTed in ONE cycle, so a tick stays bounded.

    Hitting it is NOT a failure: the cursor advances over every page that landed, so the
    next cycle resumes exactly where this one stopped. That is what lets a box with a
    huge backlog converge in steps instead of timing out forever on one giant attempt.
    """
    return max(1, int(getattr(settings, "RMC_EDGE_SYNC_MAX_PAGES_PER_CYCLE", 20) or 20))


def _chunk(rows, size):
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _row_high_water(rows):
    """Newest ``updated_at`` in ``rows`` as a datetime, or None.

    Rows carry ISO strings (that is what goes on the wire), so this parses rather than
    assuming; an unparseable/absent stamp yields None and simply does not advance a
    cursor, which is the safe direction.
    """
    from django.utils.dateparse import parse_datetime

    best = None
    for row in rows:
        raw = row.get("updated_at")
        parsed = parse_datetime(raw) if isinstance(raw, str) else raw
        if parsed is None:
            continue
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        if best is None or parsed > best:
            best = parsed
    return best


def _resolve_principal(school):
    """Local admin principal to apply pulled rows as — mirrors ``pull_edge_inbox``'s
    resolver (school owner, else any superuser)."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        from apps.schools.models import SchoolMembership

        owner = (
            SchoolMembership.objects.filter(school=school, role="owner")
            .select_related("user")
            .first()
        )
        if owner is not None and getattr(owner, "user", None) is not None:
            return owner.user
    except Exception:  # noqa: BLE001 — membership model shape varies; fall through
        pass
    return User.objects.filter(is_superuser=True).order_by("pk").first()


def _pulse_sync(school, *, processed: int, expected: int, log_message: str, status: str = ""):
    """Best-effort live canvas pulse. Never raises, never uses float()."""
    try:
        from apps.platform_runtime.workflow_telemetry import (
            TASK_EDGE_SYNC,
            update_and_broadcast_progress,
        )

        update_and_broadcast_progress(
            school=school,
            workflow_key="siteconfig-edge-sync",
            task_type=TASK_EDGE_SYNC,
            processed=processed,
            expected=max(int(expected or 0), 1),
            log_message=log_message,
            status=status,
        )
    except Exception:  # noqa: BLE001 — telemetry must never break a sync cycle
        pass


def run_sync_cycle(school, *, mode="live", run_row=None) -> dict:
    """Run one edge<->cloud sync cycle for ``school`` and record exactly one EdgeSyncRun.

    NEVER raises. Returns a result dict:
    ``{enabled, mode, ok, pushed, pulled, conflicts, created, upserted, message, error}``.

    Pass ``run_row`` when the HTTP view already opened the in-progress row so
    status polling can see **running** before the worker starts. A row that
    another click already abandoned (``finished_at`` set) is a no-op.
    """
    from apps.sync_engine.models import EdgeSyncRun

    mode = "dry" if str(mode).strip().lower() == "dry" else "live"
    started = timezone.now()
    result = {
        "enabled": True,
        "mode": mode,
        "ok": False,
        "pushed": 0,
        "pulled": 0,
        "conflicts": 0,
        "created": 0,
        "upserted": 0,
        # Rows REMOVED because a deletion crossed the boundary. Reported separately from
        # every other count because it is the only one that destroys data.
        "deleted": 0,
        # Rows the far side accepted into the bundle but this side could NOT apply (an
        # absent parent, a held entity, a value the local schema refuses). Counted
        # separately from conflicts because nobody is being asked to choose - the row
        # simply did not land, and a cycle that reports only "pulled N" would present that
        # as success.
        "skipped": 0,
        "message": "",
        "error": "",
    }

    if run_row is not None:
        try:
            run_row.refresh_from_db()
        except Exception:  # noqa: BLE001 — missing row is treated as a fresh begin
            run_row = None
        if run_row is not None and run_row.finished_at is not None:
            result["ok"] = True
            result["message"] = "superseded by a newer cycle"
            return result

    # Flag-gated exactly like edge_sync_cycle: off => a hard no-op (no network), but we
    # still record a visible ok=False row so the UI can explain why nothing happened.
    if not getattr(settings, "RMC_EDGE_SYNC_ENABLED", False):
        result["enabled"] = False
        result["message"] = "Edge sync is not enabled on this deployment"
        if run_row is not None:
            run_row.complete(
                mode=mode,
                ok=False,
                message=result["message"],
                started_at=getattr(run_row, "started_at", None) or started,
            )
        else:
            EdgeSyncRun.record(
                school,
                mode=mode,
                ok=False,
                message=result["message"],
                started_at=started,
                finished_at=timezone.now(),
            )
        return result

    if run_row is None:
        run_row = EdgeSyncRun.begin(school, mode=mode)
    try:
        _run_sync_cycle_body(school, mode=mode, result=result, run_row=run_row)
    except Exception as exc:  # noqa: BLE001 — the public runner never raises
        result["ok"] = False
        result["error"] = str(exc)
        result["message"] = result["message"] or "Sync finished with errors"
    finally:
        if run_row.finished_at is None:
            run_row.complete(
                mode=mode,
                ok=result["ok"],
                pushed=result["pushed"],
                pulled=result["pulled"],
                conflicts=result["conflicts"],
                created=result["created"],
                upserted=result["upserted"],
                deleted=result["deleted"],
                skipped=result["skipped"],
                message=result["message"],
                error=result["error"],
            )
    return result


def _run_sync_cycle_body(school, *, mode, result, run_row) -> None:
    from contextlib import nullcontext

    from django.db import connection

    try:
        from apps.platform_runtime.workflow_tracker import ensure_workflow_run

        schema = str(getattr(connection, "schema_name", "") or "")
        tracker = ensure_workflow_run(
            "siteconfig-edge-sync",
            steps=("push", "pull"),
            expected_duration_seconds=180,
            school_id=str(getattr(school, "pk", "") or ""),
            tenant_schema=schema,
            payload={"task_type": "EDGE_SYNC"},
        )
    except Exception:  # noqa: BLE001 — tracking must never block the cycle
        tracker = nullcontext()
    with tracker:
        _pulse_sync(
            school,
            processed=0,
            expected=2,
            log_message="Starting edge sync cycle",
            status="running",
        )
        _execute_sync_transport(school, mode=mode, result=result, run_row=run_row)
        _pulse_sync(
            school,
            processed=2,
            expected=2,
            log_message=result.get("message") or "Sync cycle finished",
            status="succeeded" if result.get("ok") else "failed",
        )


def _execute_sync_transport(school, *, mode, result, run_row) -> None:
    base = _operator_base()
    token = _edge_token()
    errors: list[str] = []
    notes: list[str] = []

    # A box that pulled new code but never ran migrate cannot apply rows for any column it
    # does not have yet. Those rows now degrade individually (sync_services catches
    # OperationalError/ProgrammingError per row) instead of killing the bundle - but the
    # operator still has to be TOLD, or they see "12 NOT applied" with no cause. Named
    # first so it heads the run message.
    try:
        from apps.sync_engine import schema_guard

        drift = schema_guard.drift_note()
        if drift:
            notes.append(f"WARNING: {drift}")
            result["schema_behind"] = True
    except Exception:  # noqa: BLE001 - a diagnostic must never break the cycle
        logger.debug("schema drift check failed", exc_info=True)

    from apps.sync_engine import edge_outbox

    # 1) PUSH local changes UP, IN PAGES, from the durable push cursor. A failure here
    #    does NOT abort the pull. In dry mode we build the delta to preview the count but
    #    NEVER post it and never move a cursor (no cloud-bound write).
    #
    #    Paging is not an optimisation, it is the difference between working and not: the
    #    receiver caps one bundle at RMC_SYNC_BUNDLE_MAX_ROWS and rejects an oversized one
    #    WHOLE (400 bundle_too_large), so the single unbounded bundle this used to send
    #    made a large backlog permanently unpushable — the further behind a box fell, the
    #    more certain every future attempt was to fail.
    try:
        from apps.sync_engine.delta_bundle import export_delta_bundle
        from apps.sync_engine.models import (
            EdgeSyncCursor,
            get_sync_cursor_for_request,
            set_sync_cursor,
        )

        # Ask from slightly BEHIND the stored high-water. A transaction that commits
        # after a concurrent cycle read the cursor stamps an updated_at already behind
        # it and would otherwise never be offered again - lost, not delayed. Re-asking
        # over a short overlap closes that (and the same-tick tie at a page boundary);
        # every apply path is idempotent, so a re-shipped row costs bandwidth only.
        # See models.get_sync_cursor_for_request for the bound this does NOT close.
        # Before rebuilding anything, settle any push whose outcome we never learned.
        # A previous cycle that died on a timeout or a 502 may have been fully applied
        # upstream; asking costs one small GET, while assuming the worst costs the whole
        # page again over a link that has already proven unreliable. Confirmed pages
        # advance the cursor here, so build_edge_delta_rows below does not re-offer them.
        try:
            from apps.sync_engine.push_confirmation import resolve_pending

            settled = resolve_pending(
                school,
                base=base,
                token=token,
                set_cursor=lambda hw: set_sync_cursor(school, EdgeSyncCursor.PUSH, hw),
            )
            if settled.get("confirmed"):
                notes.append(
                    f"{settled['confirmed']} earlier push(es) confirmed already "
                    f"applied upstream; not re-sent"
                )
        except Exception:  # noqa: BLE001 — never let the optimisation block the push
            logger.debug("push confirmation sweep failed", exc_info=True)

        push_since = get_sync_cursor_for_request(school, EdgeSyncCursor.PUSH)
        rows, meta = edge_outbox.build_edge_delta_rows(school, since=push_since, entities=None)

        # The overlap re-offers everything changed inside the window. Paid for naively
        # that would re-transmit each recent row on EVERY tick — six times per row at a
        # 20s cadence, on a link a school may be paying for by the megabyte — and would
        # undo the guarantee that a second cycle with no local change pushes nothing.
        # So drop a re-offer whose exact version this side already delivered. A genuine
        # edit carries a different updated_at and still ships; a row lost to the race the
        # overlap exists for was never sent, so it is not in this memory at all.
        from apps.sync_engine import push_ledger

        _sent_memory = push_ledger.recent_sent(school)
        if _sent_memory:
            rows = [r for r in rows if not push_ledger.already_sent(_sent_memory, r)]
            meta["row_count"] = len(rows)

        # Offline-CREATED rows travel TOGETHER. apply_edge_inserts remaps a
        # new-references-new FK using an in-bundle (entity_type, local_pk) -> operator_pk
        # map and DROPS the FK when the referent is not in the same bundle, so splitting
        # them would silently unlink a child from the parent it was created with. Updates
        # are keyed by pk and order-independent, so they page freely.
        # A DELETION row is keyed by pk and is idempotent, so it pages with the updates
        # even when it carries an anchor. Grouping it with the inserts instead would put
        # it in the block that deliberately does NOT advance the cursor, so a cycle that
        # shipped only deletions would re-ship them every time.
        from apps.sync_engine.tombstones import DELETE_OP

        def _is_delete(row):
            return str(row.get("op") or "").strip().lower() == DELETE_OP

        inserts, updates = [], []
        for _row in rows:
            if (_row.get("client_offline_id") or "").strip() and not _is_delete(_row):
                inserts.append(_row)
            else:
                updates.append(_row)

        if mode == "dry":
            notes.append(f"dry run: {meta['row_count']} local change(s) NOT pushed")
        elif meta["row_count"] == 0:
            notes.append("nothing to push")
        else:
            endpoint = _endpoint(base, "api:sync-bundle-upload")
            page_size = _page_size()
            max_pages = _max_pages_per_cycle()

            # Inserts go FIRST and, wherever they fit, whole. Sending them ahead of the
            # updates is what makes an update page's high-water a valid cursor: every
            # older row — insert or update — is already on the wire by then.
            insert_pages = list(_chunk(inserts, page_size)) if inserts else []
            if len(insert_pages) > 1:
                notes.append(
                    f"WARNING: {len(inserts)} offline-created rows exceed the "
                    f"{page_size}-row bundle cap and had to be split across "
                    f"{len(insert_pages)} bundles; a new-references-new link whose "
                    "target lands in another bundle is dropped rather than mis-linked"
                )
            pages = insert_pages + list(_chunk(updates, page_size))

            posted_pages = 0
            drained_updates = True
            for index, page in enumerate(pages):
                if posted_pages >= max_pages:
                    drained_updates = False
                    remaining = sum(len(p) for p in pages[index:])
                    notes.append(
                        f"{remaining} row(s) deferred to the next cycle "
                        f"(page ceiling {max_pages} reached)"
                    )
                    break
                data = export_delta_bundle(
                    school_id=str(school.id), rows=page, device_id="edge"
                )
                status, body = edge_outbox.post_bundle(endpoint, token, data)
                if status == 400 and "bundle_too_large" in (body.get("errors") or []):
                    # The operator's cap is lower than ours. It tells us its real limit;
                    # believe IT rather than our local setting, and stop this cycle so the
                    # next one re-pages the remainder from the unmoved cursor.
                    errors.append(
                        f"push page rejected as too large; operator cap is "
                        f"{body.get('max_rows')} rows (local page size {page_size}) — "
                        "set RMC_SYNC_BUNDLE_MAX_ROWS to match"
                    )
                    drained_updates = False
                    break
                if not (status == 200 and body.get("ok")):
                    from apps.sync_engine.connectivity_probe import format_http_rejection
                    from apps.sync_engine.push_confirmation import (
                        is_ambiguous_failure,
                        record_ambiguous_push,
                    )

                    rejection = format_http_rejection("push", status, body)
                    errors.append(rejection)
                    if is_ambiguous_failure(status):
                        # A timeout or a gateway error means the answer was LOST, not
                        # that the answer was no — the cloud may have applied this
                        # page. Remember the nonce so the next cycle can ask instead
                        # of re-shipping the whole page over a link that just failed.
                        record_ambiguous_push(
                            school,
                            data=data,
                            high_water=(
                                _row_high_water(page) if index >= len(insert_pages) else ""
                            ),
                            row_count=len(page),
                            failure=rejection[:120],
                        )
                    drained_updates = False
                    break
                posted_pages += 1
                push_ledger.record_sent(school, page)
                result["pushed"] += len(page)
                result["conflicts"] += int(body.get("conflicts") or 0)
                # Advance only over the ground actually covered. Inserts carry no safe
                # global position on their own (an insert may be older than an update we
                # have not sent yet), so the cursor moves on UPDATE pages only — by which
                # point every insert is already delivered.
                if index >= len(insert_pages):
                    set_sync_cursor(school, EdgeSyncCursor.PUSH, _row_high_water(page))

            if drained_updates and not errors:
                # Everything in this window landed: park the cursor on the window's own
                # high-water so an echo-suppressed row (scanned but deliberately not sent)
                # cannot be re-scanned forever.
                set_sync_cursor(school, EdgeSyncCursor.PUSH, meta.get("high_water"))
            if result["pushed"]:
                notes.append(f"pushed {result['pushed']} in {posted_pages} bundle(s)")
        # Dry, empty, and live push all share the same 1/2 pulse so the poll bar
        # matches telemetry (row counts stay on pushed/pulled, not percent).
        push_note = notes[-1] if notes else "Push phase finished"
        run_row.checkpoint(
            pushed=result["pushed"],
            conflicts=result["conflicts"],
            message=push_note,
        )
        _pulse_sync(
            school,
            processed=1,
            expected=2,
            log_message=push_note,
            status="running",
        )
    except Exception as exc:  # noqa: BLE001 — never crash the tenant page
        errors.append(f"push failed: {exc}")

    # 2) PULL cloud changes DOWN. LIVE applies them (inbound/local; cloud is
    #    authoritative). DRY only confirms the cloud is reachable and the credential is
    #    accepted (HTTP 200) and applies NOTHING — a true no-write probe. Independent of
    #    the push result either way.
    try:
        from django.utils.dateparse import parse_datetime

        from apps.sync_engine.models import (
            EdgeSyncCursor,
            get_sync_cursor_for_request,
            set_sync_cursor,
        )

        endpoint = _endpoint(base, "api:sync-bundle-download")
        # Same overlap as the push leg, for the same reason - a row written on the cloud
        # while a cycle was in flight must not fall permanently behind the cursor.
        pull_since = get_sync_cursor_for_request(school, EdgeSyncCursor.PULL)
        collected: dict = {}
        # G8: on the cycles a parity sweep is due, state what this box HOLDS so the cloud
        # can answer with what disagrees. Skipped in DRY mode — a dry run is a no-write
        # reachability probe, and the repair it would discover is one it may not perform,
        # so spending a full-corpus scan there buys an answer nothing can act on.
        parity_header = ""
        if mode != "dry":
            try:
                from apps.sync_engine import parity as _parity

                if _parity.due(school):
                    parity_header = _parity.encode_digests(_parity.parity_digests(school))
                    logger.info(
                        "edge sync: parity sweep for school=%s covering %s entities",
                        school.pk,
                        len(parity_header.split(",")) if parity_header else 0,
                    )
            except Exception:  # noqa: BLE001 — a sweep must never cost the box its pull
                logger.debug("parity sweep skipped", exc_info=True)
        status, body, high_water = edge_outbox.pull_bundle(
            endpoint,
            token,
            since=pull_since,
            entities=None,
            collect=collected,
            parity=parity_header,
        )

        # A cloud operator cannot reach into this box, so a "resync everything" request
        # arrives as a header on the box's OWN download. Honour it by rewinding both
        # cursors: the NEXT cycle then replays the whole corpus through the ordinary,
        # idempotent apply path. Deliberately not applied to this cycle's bundle, which was
        # already built against the old cursor and is only a delta.
        # G4: the cloud tells the box, on the same response, which entities it withheld
        # because this box has not migrated yet. Named in the run message so an operator
        # sees "attendance is frozen until you migrate" instead of silently missing data.
        schema_advice = (collected.get("schema_advice") or "").strip()
        withheld_entities = collected.get("withheld_entities") or []
        if schema_advice or withheld_entities:
            result["schema_behind"] = True
            note = f"WARNING: {schema_advice}" if schema_advice else "WARNING: schema skew"
            if withheld_entities:
                note += f" [withheld: {', '.join(sorted(withheld_entities))}]"
            notes.append(note)

        directive = (collected.get("directive") or "").strip()
        resyncing = directive == "full-resync" and mode != "dry"
        if resyncing:
            from apps.sync_engine.models import reset_sync_cursors

            rewound = reset_sync_cursors(school)
            # A resync means "send everything again", so a memory of what was already
            # sent is precisely the thing that would defeat it.
            from apps.sync_engine import push_ledger as _push_ledger

            _push_ledger.reset(school)
            # Rewinding is only half of it. The replay happens on the NEXT cycle, and
            # without a wake that cycle waits out the adaptive cadence — which backs OFF
            # precisely for the quiet box an operator is most likely to be resyncing. So
            # the operator pressed a button, the box obeyed instantly, and nothing
            # visible happened for minutes. Raise the wake so the replay starts on the
            # next tick (seconds), not the next interval.
            try:
                from apps.sync_engine import cadence

                cadence.request_wake("cloud requested full resync")
            except Exception:  # noqa: BLE001 — a missed wake costs latency, not data
                logger.debug("sync_runner: could not raise the resync wake", exc_info=True)
            notes.append(
                f"full resync requested by the cloud: rewound {rewound} cursor(s); "
                "the next cycle replays the entire corpus"
            )

        if status != 200:
            from apps.sync_engine.connectivity_probe import format_http_rejection

            errors.append(format_http_rejection("pull", status, body))
        elif mode == "dry":
            notes.append("cloud reachable, credential accepted (no changes applied)")
        else:
            from apps.sync_engine.edge_inbox import apply_pulled_bundle

            user = _resolve_principal(school)
            if user is None:
                errors.append("pull skipped: no local principal to apply as")
            else:
                applied = apply_pulled_bundle(school, user, body, origin="cloud-pull")
                if not applied.get("ok"):
                    errors.append(f"pull verification failed: {applied.get('errors')}")
                else:
                    result["pulled"] = int(applied.get("received") or 0)
                    result["created"] += int(applied.get("created") or 0)
                    result["upserted"] += int(applied.get("upserted") or 0)
                    result["deleted"] += int(applied.get("deleted") or 0)
                    result["conflicts"] += int(applied.get("conflicts") or 0)
                    result["skipped"] += int(applied.get("skipped") or 0)
                    # The download endpoint has always stamped the new high-water in
                    # X-RMC-Sync-High-Water so the box can advance; the runner used to
                    # throw it away and re-request the whole corpus every 180s. Advance
                    # only AFTER a verified apply, so a rejected or unverifiable bundle
                    # leaves the position put and the rows are re-offered next cycle.
                    # Do NOT advance when a resync was just requested: this bundle is only
                    # the delta from the OLD cursor, so recording its high-water here would
                    # silently cancel the rewind we performed moments ago.
                    parsed = parse_datetime(high_water) if (high_water and not resyncing) else None
                    if parsed is not None:
                        if timezone.is_naive(parsed):
                            parsed = timezone.make_aware(
                                parsed, timezone.get_current_timezone()
                            )
                        set_sync_cursor(school, EdgeSyncCursor.PULL, parsed)
                    note = (
                        f"pulled {result['pulled']} (created {result['created']}, "
                        f"upserted {result['upserted']}, conflicts {result['conflicts']})"
                    )
                    if result["deleted"]:
                        # Named explicitly. A cycle that removed records must never be
                        # summarised only as "pulled N" - the one number an operator has
                        # to be able to see is how many rows this cycle destroyed.
                        note += f"; DELETED {result['deleted']} record(s)"
                    if result["skipped"]:
                        # Named reasons, not just a count: "3 not applied" sends an operator
                        # hunting, "missing_reference x3" says which rail is broken and why.
                        reasons = applied.get("skipped_reasons") or {}
                        detail = ", ".join(
                            f"{k} x{v}" for k, v in sorted(reasons.items())
                        )
                        note += f"; {result['skipped']} NOT applied"
                        if detail:
                            note += f" ({detail})"
                    notes.append(note)
                    if (applied.get("skipped_reasons") or {}).get("missing_reference"):
                        # Rewinding LAST, after the high-water advance above, so the rewind
                        # is what survives this cycle.
                        notes.append(_request_replay_for_missing_parents(school))

                    # G8: the cloud answered this cycle's parity digest with the entities
                    # whose contents disagree. Repair them, narrowly, and SAY so — an
                    # operator who is never told the two sides had diverged cannot know
                    # the box was serving stale records until now.
                    drifted = collected.get("parity_drift") or []
                    if drifted:
                        result["parity_drift"] = list(drifted)
                        advice = (collected.get("parity_advice") or "").strip()
                        logger.warning(
                            "edge sync: parity drift for school=%s entities=%s (%s)",
                            school.pk,
                            ",".join(drifted),
                            advice or "no detail",
                        )
                        notes.append(advice or f"parity drift: {', '.join(drifted)}")
                        flush_note = _flush_drifted_entities(
                            school, endpoint, token, user, drifted
                        )
                        if flush_note:
                            notes.append(flush_note)
                        # Re-sweep on the NEXT cycle rather than in an hour: the repair
                        # either worked or it did not, and that answer is worth having
                        # promptly. It also closes the loop honestly — a flush that
                        # silently failed would otherwise read as a fix for an hour.
                        try:
                            from apps.sync_engine import parity as _parity

                            _parity.reset(school)
                        except Exception:  # noqa: BLE001 — costs latency, not data
                            logger.debug("could not re-arm the parity sweep", exc_info=True)
    except Exception as exc:  # noqa: BLE001 — never crash the tenant page
        errors.append(f"pull failed: {exc}")

    result["ok"] = not errors
    result["error"] = "; ".join(errors)
    result["message"] = "; ".join(notes) or (
        "Sync complete" if result["ok"] else "Sync finished with errors"
    )
    run_row.checkpoint(
        pushed=result["pushed"],
        pulled=result["pulled"],
        conflicts=result["conflicts"],
        created=result["created"],
        upserted=result["upserted"],
        deleted=result["deleted"],
        skipped=result["skipped"],
        message=result["message"],
        error=result["error"],
    )


__all__ = ["run_sync_cycle"]
