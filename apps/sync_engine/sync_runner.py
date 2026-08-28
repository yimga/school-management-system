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
from typing import NamedTuple

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


def _rail_model_labels() -> set:
    """``{"app.Model"}`` for every entity the delta rail carries.

    Answers the only question the replay decision needs: could a replay ever produce this
    parent? Derived from the live registry rather than listed, so an entity added to the
    rail is replayable the day it is added and nothing here has to be remembered.
    """
    from apps.api.sync_services import _get_entity_config

    return {
        model._meta.label
        for model, _allowed in _get_entity_config(include_derived=True).values()
    }


def _rail_entity_by_model_label() -> dict:
    """``{"academics.Department": "department", ...}`` from the LIVE registry.

    The inbox reports an absent parent by its model label, and a repair has to ask for
    it by entity type. Derived rather than listed, so an entity added to the rail is
    repairable the day it is added with nothing here to remember.
    """
    from apps.api.sync_services import _get_entity_config

    return {
        model._meta.label: entity_type
        for entity_type, (model, _allowed) in _get_entity_config(
            include_derived=True
        ).items()
    }


def _request_replay_for_missing_parents(
    school, parents=None, *, endpoint=None, token=None, user=None
) -> str:
    """Fetch the tables the absent parents live in - not the whole corpus.

    A ``missing_reference`` means the bundle carried a CHILD whose PARENT this box does not
    have. When the parent's table RIDES THE RAIL, the parent is absent only because its own
    ``updated_at`` is older than the pull cursor, so an incremental delta will never offer it
    again - the child would be refused on every future cycle and the two sides would stay
    silently divergent. The parent has to be fetched by some means other than the delta.

    IT DOES NOT TAKE THE WHOLE CORPUS TO FETCH ONE TABLE. Rewinding the cursor to 'no
    position' re-downloads every row of every entity - 315,964 of them on the box this
    was measured on, to collect one absent department - and because a full-corpus pull re-offers every row
    the box already holds, the replay is itself what drove waves of conflict and skip
    records through the apply path. The cure was the disease.

    So the repair asks for the ENTITY the parent lives in, whole, with ``since=None``, and
    leaves the cursor exactly where it was. That is ``_flush_drifted_entities``, which G8
    already uses for the same reason and whose docstring says it plainly: rewinding
    "replays the ENTIRE corpus to repair one table, which on a metered link is a bill and
    on a large school is an hour". It rides the ordinary rail end to end, so a row this
    side must not lose is protected by exactly the guards that protect it on every other
    cycle - a narrow pull, not a privileged repair channel.

    The rewind remains as the fallback for a caller that cannot do better: without
    ``endpoint``/``token``/``user`` there is nothing to ask, and without ``parents`` there
    is no way to know which table to ask for.

    WHEN THE PARENT'S TABLE DOES NOT RIDE, none of that is true and the rewind is worse than
    useless. A replay cannot carry a row the rail never carries, so the reference is still
    unresolvable on the next cycle and on every cycle after it - and the price of finding
    that out is re-downloading the ENTIRE corpus, once per cooldown, indefinitely. That is
    not a healing step, it is a loop with a bandwidth bill; and because a full-corpus pull
    re-offers every row the box already holds, it is also what drove waves of avoidable
    conflict and skip records through the apply path.

    So the rewind now depends on the evidence: rewind when at least one absent parent is a
    row a replay could produce, and otherwise REPORT the unreachable parents by name and
    leave the cursor where it is. An unreachable parent is a real gap and it is stated as
    one, because the fix for it is a rail change, not another download.

    ``parents`` is ``{model_label: count}`` from the inbox. Omitted (the pre-existing
    signature) means 'no evidence either way', which keeps the historical behaviour of
    rewinding - a caller that cannot say must not be silently downgraded to doing nothing.

    Returns the note to show the operator. Never raises: a healing step must not be the
    thing that breaks a sync cycle.
    """
    from django.core.cache import cache

    from apps.sync_engine.models import EdgeSyncCursor, reset_sync_cursors

    try:
        unreachable = []
        if parents:
            try:
                on_rail = _rail_model_labels()
            except Exception:  # noqa: BLE001 - cannot classify, so do not downgrade
                logger.debug("could not read the rail registry", exc_info=True)
                on_rail = None
            if on_rail is not None:
                unreachable = sorted(set(parents) - on_rail)
                if len(unreachable) == len(set(parents)):
                    # Every absent parent lives in a table the rail does not carry.
                    return (
                        "records reference "
                        + ", ".join(unreachable)
                        + ", which this rail does not carry; a replay cannot produce them, "
                        "so the pull cursor was left alone. Landing these rows needs a rail "
                        "change, not another sync"
                    )

        # THE NARROW REPAIR. Everything needed to ask for exactly the right tables:
        # which parents are missing, and a way to ask. Anything absent falls through to
        # the corpus rewind below rather than being quietly downgraded to doing nothing.
        if parents and endpoint and token and user is not None:
            by_label = {}
            try:
                by_label = _rail_entity_by_model_label()
            except (ImportError, LookupError, AttributeError, TypeError):
                # Named: the registry is an import plus model lookups, and a blanket
                # except here would swallow a bug in the mapping and silently downgrade
                # every repair to a full-corpus rewind -- the exact behaviour being
                # removed, restored invisibly.
                logger.debug("could not map parent labels to entities", exc_info=True)
            wanted, cooling = [], []
            for label in sorted(set(parents)):
                entity_type = by_label.get(label)
                if not entity_type:
                    continue  # off-rail; already reported as unreachable above
                # Per ENTITY, not per school: a department that cannot be repaired must
                # not also block a classroom that can.
                if cache.add(
                    _MISSING_REF_REPLAY_KEY % f"{school.pk}:{entity_type}",
                    1,
                    _MISSING_REF_REPLAY_COOLDOWN_SECONDS,
                ):
                    wanted.append(entity_type)
                else:
                    cooling.append(entity_type)
            if wanted or cooling:
                bits = []
                if wanted:
                    outcome = _flush_drifted_entities(school, endpoint, token, user, wanted)
                    bits.append(
                        outcome.note
                        or "requested " + ", ".join(wanted) + " to collect the missing parents"
                    )
                if cooling:
                    bits.append(
                        ", ".join(sorted(cooling))
                        + " was requested recently, so this cycle did not request it again"
                    )
                if unreachable:
                    bits.append(
                        ", ".join(unreachable)
                        + " is not carried by this rail and no request will produce it"
                    )
                # The cursor is untouched on this path, on purpose: nothing else re-ships.
                return "; ".join(b for b in bits if b)

        key = _MISSING_REF_REPLAY_KEY % school.pk
        # cache.add only succeeds when the key is absent, so the cooldown is atomic even if
        # two cycles overlap.
        if not cache.add(key, 1, _MISSING_REF_REPLAY_COOLDOWN_SECONDS):
            return (
                "records are still waiting on a parent this box has not received; a full "
                "replay was requested recently, so this cycle did not request another"
            )
        reset_sync_cursors(school, direction=EdgeSyncCursor.PULL)
        note = (
            "records referenced a parent this box does not have; rewound the pull cursor "
            "so the next cycle replays the full corpus and collects the missing parents"
        )
        if unreachable:
            # A replay WILL help some of them, so the rewind stands - but saying only that
            # would report a repair that is partial as if it were complete.
            note += (
                ". Not all of them: "
                + ", ".join(unreachable)
                + " is not carried by this rail and no replay will produce it"
            )
        return note
    except Exception as exc:  # noqa: BLE001 - healing must never break the cycle
        logger.debug("replay request for missing parents failed", exc_info=True)
        return f"could not request a replay for the missing parents: {exc}"

class FlushOutcome(NamedTuple):
    """What the parity flush actually did, not just what it would say about it.

    The note alone was the whole return value, so the caller could only append it and
    re-arm the sweep unconditionally — including after a flush that had detected, and
    said in that very note, that it could NOT repair. ``repaired``/``failed`` make the
    outcome something a caller can decide on.
    """

    note: str
    repaired: list
    failed: list


def _flush_drifted_entities(school, endpoint, token, user, drifted) -> FlushOutcome:
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

    Returns a :class:`FlushOutcome`. Never raises: a repair must not be the thing
    that breaks the cycle it is repairing.
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
        # A setup failure repaired nothing, so it is reported as a failure of every
        # entity that was asked for, not as an empty outcome - an empty outcome
        # reads as "no drift left" to the caller that decides the re-arm.
        return FlushOutcome(
            f"parity flush could not start: {exc}", [], [str(e) for e in (drifted or [])]
        )
    if not targets:
        return FlushOutcome("", [], [])
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
        # Deferred entities are still drifted, so they belong in `failed`: a caller
        # deciding whether the drift is CLOSED must not read "we ran out of budget"
        # as "everything is fixed now" - the same mistake the note above warns of.
        failed.extend(list(drifted)[cap:])
    return FlushOutcome("; ".join(bits), repaired, failed)


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
        # OTA interlock. Always present so a caller never has to distinguish "not held"
        # from "this build predates the interlock" — the Sync Center reads both.
        "held_for_upgrade": False,
        "upgrade_target": "",
        "upgrade_available": "",
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

    # OTA INTERLOCK. The previous cycle learned from a response header that this box is
    # not built from the code the operator is serving. Move NOTHING until the upgrade has
    # been applied: a bundle applied by stale code against a schema the cloud has already
    # moved is the split-brain this whole mechanism exists to prevent.
    #
    # The cursors are deliberately left where they are, so the held ground is re-offered
    # in full on the cycle after the upgrade — a hold defers work, it never drops it.
    # The hold also EXPIRES (see upgrade_lock.hold_ttl_seconds), so a box whose upgrade
    # never completes returns to syncing on its old code rather than going quiet forever.
    #
    # A dry run is exempt: it writes nothing in either direction, and it is exactly what
    # an operator runs to ask "can this box still reach the cloud" while the box is held.
    if mode != "dry":
        try:
            from apps.sync_engine import upgrade_lock

            hold = upgrade_lock.local_state()
            if hold.get("state") == upgrade_lock.SYNC_STATE_HELD_FOR_UPGRADE:
                target = str(hold.get("target_hash") or "")[:12]
                result["held_for_upgrade"] = True
                result["upgrade_target"] = str(hold.get("target_hash") or "")
                # ok=True: nothing failed. The box did exactly what it should have done.
                # Reporting this as an error would train an operator to ignore red rows
                # during every upgrade window.
                result["ok"] = True
                result["message"] = (
                    f"held for upgrade -> {target} ({hold.get('held_seconds', 0)}s); "
                    "data sync resumes once the upgrade is applied"
                )
                logger.info(
                    "edge sync: school=%s held for upgrade target=%s",
                    getattr(school, "pk", None),
                    target,
                )
                return
        except Exception:  # noqa: BLE001 - the interlock must never be what breaks a cycle
            logger.debug("upgrade interlock check failed", exc_info=True)

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

        # OTA: the cloud named a manifest this box is not on. Arming is all that happens
        # here — the current cycle is already complete and was protected by the schema
        # handshake; the hold takes effect on the NEXT tick, which costs nothing and
        # keeps the learning path free of an extra round trip.
        manifest_target = (collected.get("manifest_target") or "").strip()
        if manifest_target and mode != "dry":
            try:
                from apps.sync_engine import local_upgrade, upgrade_lock
                from apps.sync_engine.system_manifest import local_manifest_hash

                if manifest_target != local_manifest_hash():
                    result["upgrade_available"] = manifest_target
                    notes.append(
                        (collected.get("manifest_advice") or "").strip()
                        or f"upgrade available: {manifest_target[:12]}"
                    )
                    # A hold is only justified when this box is going to ACT on it in a
                    # way that could produce split-brain. That is the FULL lane and only
                    # the full lane.
                    #
                    # With RMC_OTA_AUTO_APPLY off, nothing on the box will apply anything
                    # until a human runs `edge_apply_upgrade`, so holding would stop a
                    # school's records from syncing for as long as an operator takes to
                    # notice — strictly worse than running one release behind, and worse
                    # than the drift it is guarding against. So the mismatch is REPORTED
                    # on every cycle and the rail keeps moving.
                    #
                    # ASSETS mode does not hold either, and that is the important case now
                    # that it is the default. The hold exists because the DATABASE may be
                    # mid-migration; an asset lane carries no migration and no python, so
                    # there is no schema to be mid-anything. Holding a school's data sync
                    # to deliver a stylesheet would be pure cost. Row-level safety in the
                    # skew case is already handled precisely, and one layer up: the
                    # cloud's `_schema_handshake` withholds exactly the entities owned by
                    # an app the box is behind on, and lets everything else through.
                    #
                    # `acknowledged_target` is the second half of the same idea: once the
                    # box has carried a target as far as its mode allows (an assets-only
                    # lane, or a code lane that needs an image rebuild), re-holding for it
                    # every cycle would be a permanent outage for a thing the box cannot
                    # finish. It stays visible; it stops being a blocker.
                    if (
                        local_upgrade.auto_apply_mode() == local_upgrade.MODE_FULL
                        and manifest_target != upgrade_lock.acknowledged_target()
                    ):
                        upgrade_lock.arm_local(
                            target_hash=manifest_target,
                            current_hash=local_manifest_hash(),
                            reason=(collected.get("manifest_advice") or "").strip(),
                        )
            except Exception:  # noqa: BLE001 - advisory; never cost the box its data
                logger.debug("could not arm the upgrade hold", exc_info=True)

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
                        # is what survives this cycle. The parent LABELS ride along so the
                        # decision can tell a parent a replay would deliver from one no
                        # replay ever will.
                        # endpoint/token/user are what turn this from a corpus
                        # rewind into a request for the one table the parent lives in.
                        notes.append(_request_replay_for_missing_parents(
                            school,
                            applied.get("skipped_missing_parents") or {},
                            endpoint=endpoint,
                            token=token,
                            user=user,
                        ))

                    # G8: the cloud answered this cycle's parity digest with the entities
                    # whose contents disagree. Repair them, narrowly, and SAY so — an
                    # operator who is never told the two sides had diverged cannot know
                    # the box was serving stale records until now.
                    drifted = collected.get("parity_drift") or []
                    try:
                        from apps.sync_engine import parity as _parity
                    except Exception:  # noqa: BLE001 — costs latency, not data
                        _parity = None
                        logger.debug("parity module unavailable", exc_info=True)
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
                        repeat = _parity.record_drift(school, drifted) if _parity else False
                        if repeat:
                            # The same entities came back drifted after a flush already
                            # ran on them. A second re-pull of the same whole tables buys
                            # the same answer at the same cost, so stop repairing and make
                            # it an operator's problem — which is what it now is.
                            result["parity_unrepairable"] = True
                            notes.append(
                                "parity drift is unrepairable by the automatic flush "
                                f"({', '.join(drifted)}): the same entities disagreed on two "
                                "consecutive sweeps. No further flush will be attempted — "
                                "an operator needs to look at this box."
                            )
                            logger.error(
                                "edge sync: parity drift unrepairable school=%s entities=%s",
                                school.pk,
                                ",".join(drifted),
                            )
                        else:
                            flush = _flush_drifted_entities(
                                school, endpoint, token, user, drifted
                            )
                            if flush.note:
                                notes.append(flush.note)
                            # Re-sweep on the NEXT cycle rather than in an hour — but ONLY
                            # when the flush actually repaired everything it was given. A
                            # re-arm skips interval_seconds() entirely, so re-arming after a
                            # flush that could not repair turns the hourly sweep into a
                            # full-corpus digest plus a whole-entity re-pull on EVERY tick,
                            # for as long as the drift lasts. Prompt when there is something
                            # to confirm; the ordinary interval when there is not.
                            if _parity and flush.repaired and not flush.failed:
                                try:
                                    _parity.reset(school)
                                except Exception:  # noqa: BLE001 — costs latency, not data
                                    logger.debug(
                                        "could not re-arm the parity sweep", exc_info=True
                                    )
                    elif _parity:
                        # The sides agree again: forget the drift so a future, unrelated
                        # drift is treated as a first sighting and gets its one repair.
                        _parity.clear_drift(school)
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
