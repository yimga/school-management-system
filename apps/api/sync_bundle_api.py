"""Signed sync-bundle upload — verify, then PERSIST via the delta apply path.

A LAN "data-mule" or a sovereign edge box uploads a signed NDJSON delta bundle
(the same row shape ``DeltaSyncAPI`` accepts online). This receiver verifies the
HMAC trailer + school binding, then routes the rows through
``apps.api.sync_services.apply_changes`` — the SAME tested path ``DeltaSyncAPI``
uses online — so writes actually land and per-record conflicts are recorded
(``SyncConflict``, updated_at check) for Sync Center resolution instead of the
old stub's silent ``{"imported": <count>}`` with no persistence.

The receiver is deliberately NOT gated on the local ``enable_offline_mode`` flag
(unlike ``DeltaSyncAPI``): the endpoint acts as the *receiving* side (e.g. the
operator ingesting an edge box's bundle), which need not itself be in offline
mode. Safety comes from ``apply_changes`` — it enforces per-entity edit
permission and per-row tenant scope regardless of the feature flag.

See docs/plans/TIER3_TENANT_PORTABILITY_AND_EDGE_SYNC.md (Slice 1).
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from apps.api.edge_auth import EdgeCredentialAuthentication
from apps.api.sync_services import apply_changes, apply_deletes, apply_edge_inserts
from apps.schools.tenant_api_guards import user_may_operate_on_school
from apps.sync_engine.delta_bundle import verify_and_parse_bundle
from apps.sync_engine.edge_outbox import (
    BUNDLE_CONTENT_TYPE,
    SYNC_DIRECTIVE_HEADER,
    SYNC_HIGH_WATER_HEADER,
    SYNC_PARITY_ADVICE_HEADER,
    SYNC_PARITY_DRIFT_HEADER,
    SYNC_PARITY_HEADER,
    SYNC_ROW_COUNT_HEADER,
    SYNC_SCHEMA_ADVICE_HEADER,
    SYNC_MANIFEST_ADVICE_HEADER,
    SYNC_MANIFEST_HEADER,
    SYNC_MANIFEST_TARGET_HEADER,
    SYNC_SCHEMA_HEAD_HEADER,
    SYNC_UPGRADE_FAILURE_HEADER,
    SYNC_WITHHELD_HEADER,
    build_edge_delta_bundle,
)


def _schema_handshake(request):
    """G4: what may this peer safely be sent, given the schema it says it is on?

    Returns ``(withheld_entities: set, advice: str)``.

    DEGRADE, DO NOT REFUSE. The tempting design is to reject the whole cycle on any
    version skew. That takes a school offline for a migration it may not even need: a box
    behind only on ``finance`` can still receive attendance, timetables and marks
    perfectly well. So the comparison is per APP, and only the entities owned by an app
    the box is behind on are withheld.

    Silent on both failure and absence: a peer that sends no head header (an older
    appliance) is treated as compatible, exactly as it behaved before the handshake
    existed. A handshake that could refuse data because a diagnostic query failed would be
    a worse bug than the drift it guards against.
    """
    raw = (request.META.get("HTTP_" + SYNC_SCHEMA_HEAD_HEADER.upper().replace("-", "_")) or "").strip()
    if not raw:
        return set(), ""
    try:
        from apps.api.sync_services import entity_app_labels
        from apps.sync_engine.schema_guard import (
            compare_heads,
            decode_heads,
            describe_skew,
            local_migration_heads,
        )

        entity_apps = entity_app_labels()
        local = local_migration_heads(set(entity_apps.values()))
        comparison = compare_heads(decode_heads(raw), local)
        stale_apps = set(comparison.get("behind") or {})
        withheld = {e for e, app in entity_apps.items() if app in stale_apps}
        return withheld, describe_skew(comparison)
    except Exception:  # noqa: BLE001 - advisory only; never cost the box its data
        return set(), ""


def _manifest_handshake(request, school):
    """OTA: is this box built from the code and assets the operator is serving?

    Returns ``(target_hash, advice)`` — both empty when the box declared no manifest,
    when this deployment has none of its own, or when the two agree.

    SIBLING OF ``_schema_handshake``, NOT A REPLACEMENT FOR IT. That one asks what the
    box's DATABASE has applied and withholds rows it could not store. This one asks what
    the box's FILES are and offers it the code that would let it store them. Two boxes on
    identical migration heads can still be a whole UI release apart, and no amount of
    row-level guarding closes that.

    IT NEVER WITHHOLDS DATA. A manifest mismatch does not make a row unsafe — the schema
    handshake already covers the case where it would. All this does is set the hold flag
    and name a target, so the box can decide to upgrade before its next cycle. Failing
    silently is therefore always the right failure: the worst outcome of a broken
    manifest comparison is that a box upgrades one cycle later than it might have.
    """
    raw = (request.META.get("HTTP_" + SYNC_MANIFEST_HEADER.upper().replace("-", "_")) or "").strip()
    if not raw:
        return "", ""
    try:
        from apps.sync_engine import upgrade_lock
        from apps.sync_engine.system_manifest import load_manifest

        target = str((load_manifest() or {}).get("manifest_hash") or "")
        if not target:
            return "", ""
        if target == raw:
            upgrade_lock.release(school)
            return "", ""
        upgrade_lock.hold(
            school,
            target_hash=target,
            current_hash=raw,
            reason="manifest mismatch at bundle download",
        )
        return target, (
            f"upgrade available: box manifest {raw[:12]} -> operator {target[:12]}"
        )
    except Exception:  # noqa: BLE001 - advisory only; never cost the box its data
        return "", ""


logger = logging.getLogger(__name__)

# The box already capped what it sends; this is the receiver's own belt-and-braces so a
# malformed header cannot write an unbounded line into the operator's log.
_UPGRADE_FAILURE_LOG_MAX_CHARS = 500  # magic-number-allow: logged excerpt of a box failure


def _log_upgrade_failure(request, school) -> None:
    """Surface a box's failed upgrade in the OPERATOR's logs.

    An appliance that cannot apply an upgrade is the case where nobody is present to read
    a local log — that is the entire premise of an edge box. The box therefore attaches
    its last failure to the next request it makes, and this is where it stops being
    invisible. Logged, not stored: a durable record already exists on the box
    (``EdgeDeploymentHistory``), and minting a cloud table for a string would add a write
    to the hot path of every pull for a diagnostic nobody queries.
    """
    raw = (request.META.get("HTTP_" + SYNC_UPGRADE_FAILURE_HEADER.upper().replace("-", "_")) or "").strip()
    if not raw:
        return
    logger.warning(
        "edge upgrade FAILED on box for school=%s: %s",
        getattr(school, "pk", None),
        raw[:_UPGRADE_FAILURE_LOG_MAX_CHARS],
    )


def _stamp_manifest_handshake(resp, request, school) -> str:
    """Put the OTA target on a response, and record the operator-visible directive.

    Returns the target hash (``""`` when in parity). The ``EdgeSyncDirective`` row is an
    AUDIT record, not the delivery mechanism — the header above is what the box acts on.
    Recording it means a cloud operator can see "this box has been offered 7c41d9ba since
    Tuesday and has not come back", which a stateless header comparison cannot show.
    """
    _log_upgrade_failure(request, school)
    try:
        target, advice = _manifest_handshake(request, school)
    except Exception:  # noqa: BLE001
        return ""
    if not target:
        return ""
    resp[SYNC_MANIFEST_TARGET_HEADER] = target
    if advice:
        resp[SYNC_MANIFEST_ADVICE_HEADER] = advice
    try:
        from apps.sync_engine.models import EdgeSyncDirective

        # One pending upgrade directive per school at a time: re-offering the same target
        # on every poll would turn a slow link into an unbounded audit log.
        EdgeSyncDirective.objects.get_or_create(
            school=school,
            kind=EdgeSyncDirective.UPGRADE,
            served_at=None,
        )
    except Exception:  # noqa: BLE001 - the header is the mechanism; the row is the record
        pass
    return target


def _parity_handshake(request, school, withheld=()):
    """G8: which entities does this box hold differently from the cloud?

    Returns ``(drifted: list, advice: str)`` — both empty when the box sent no digest,
    when parity is off, or when anything at all went wrong.

    ``withheld`` (the schema handshake's answer) is excluded BEFORE the comparison is
    described, not after: there the difference is already explained and re-pulling would
    not fix it, so naming such an entity would point an operator at the wrong repair and
    burn a full-entity re-pull on it.

    COST IS OPT-IN AND BOUNDED. The cloud digests ONLY the entities the box actually
    reported, and only when it reported any. A box that never sends the header (an older
    appliance, or one whose sweep is not due) costs this endpoint a single dictionary
    lookup — which matters, because the download endpoint is on the hot path of every
    cycle for every box, while a sweep is hourly at most.

    ADVISORY, exactly like the schema handshake above: the bundle is the payload, and a
    parity answer is a bonus. Drift is REPORTED, never acted on here — the repair is the
    box's to run, because the box is the side that can re-pull.
    """
    raw = (request.META.get("HTTP_" + SYNC_PARITY_HEADER.upper().replace("-", "_")) or "").strip()
    if not raw:
        return [], ""
    try:
        from apps.sync_engine import parity

        if not parity.enabled():
            return [], ""
        skip = set(withheld or ())
        remote = {k: v for k, v in parity.decode_digests(raw).items() if k not in skip}
        if not remote:
            return [], ""
        # The BOX's digest is `remote` from the cloud's point of view. Compare in the
        # box's own orientation (local=box, remote=cloud) so `row_delta` reads as "rows
        # the cloud has that the box does not" on both sides of the wire — a sign flip
        # here would send an operator hunting for extra rows when records are missing.
        local = parity.parity_digests(school, entities=list(remote))
        comparison = parity.compare_digests(remote, local)
        return parity.rank_for_flush(comparison), parity.describe(comparison)
    except Exception:  # noqa: BLE001 - advisory only; never cost the box its data
        return [], ""


class SyncBundleRenderer(BaseRenderer):
    """Make the bundle media type NEGOTIABLE so the box's pull is not rejected 406.

    The box asks for exactly what this endpoint produces
    (``Accept: application/x-rmc-sync-bundle+ndjson``, see
    ``apps.sync_engine.edge_outbox.pull_bundle``). DRF picks a renderer in
    ``APIView.initial()`` -- BEFORE ``get()`` runs -- so with only the default JSON
    renderers registered, content negotiation raises ``NotAcceptable`` and every pull
    dies with a 406 the view never sees. The download's success path returns a plain
    ``HttpResponse``, so this renderer does no real work on it; it exists so the
    negotiation step can succeed. It is registered LAST, after the defaults, so a
    request with ``Accept: */*`` still resolves to JSON and the ``Response``-based
    400/403 branches render normally.
    """

    media_type = BUNDLE_CONTENT_TYPE
    format = "rmc-sync-bundle"
    charset = None

    def render(self, data, accepted_media_type=None, renderer_context=None):
        # Reached only if a DRF Response (an error branch) is returned while this
        # renderer is the negotiated one -- serve the payload rather than 500.
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        if data is None:
            return b""
        return json.dumps(data, default=str).encode("utf-8")


@extend_schema_view(
    post=extend_schema(
        tags=["Offline Sync"],
        summary="Upload signed sync bundle",
        description=(
            "Accepts a signed NDJSON delta bundle from an offline device / sovereign "
            "edge box; verifies the HMAC signature + school binding, then applies the "
            "rows through the delta-sync engine (updated_at conflict check; a newer "
            "server record yields a SyncConflict rather than an overwrite)."
        ),
        responses={200: dict, 400: dict, 403: dict},
    ),
)
class SyncBundleUploadView(APIView):
    # Edge machine credential FIRST (so an edge box needs no session/subdomain), then
    # the project defaults so an online session upload still authenticates normally.
    authentication_classes = [EdgeCredentialAuthentication, *api_settings.DEFAULT_AUTHENTICATION_CLASSES]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        school = getattr(request, "school", None)
        if school is None:
            return Response({"ok": False, "error": "school_required"}, status=403)
        if not user_may_operate_on_school(request, school):
            return Response({"ok": False, "error": "forbidden"}, status=403)

        data = request.body or b""
        collected: dict = {}
        rows, errors = verify_and_parse_bundle(
            data, expected_school_id=school.pk, collect=collected
        )
        if errors:
            return Response({"ok": False, "errors": errors}, status=400)

        # REPLAY DEFENCE. The signature proves who built this bundle; it says nothing
        # about whether we have already been handed it. A captured bundle re-presented
        # later verifies perfectly and can resurrect rows the far side has since deleted
        # or undo a conflict a human resolved. See apps.sync_engine.replay_guard.
        from apps.sync_engine.replay_guard import register_bundle

        replay = register_bundle(
            school, collected, direction="edge-push", row_count=len(rows)
        )
        if replay:
            return Response({"ok": False, "errors": [replay]}, status=409)

        # Bound the batch so a single sneakernet bundle can't open an unbounded
        # write transaction. Env-overridable; the online DeltaSyncAPI caps at 50.
        max_rows = int(getattr(settings, "RMC_SYNC_BUNDLE_MAX_ROWS", 500))
        if len(rows) > max_rows:
            return Response(
                {"ok": False, "errors": ["bundle_too_large"], "max_rows": max_rows},
                status=400,
            )

        # Split cloned-record UPDATES (no client_offline_id -> pk is stable across the
        # clone) from offline-CREATED rows (carry a client_offline_id; their local pk is
        # meaningless on the operator) and DELETIONS (op="delete"). Updates go by pk;
        # inserts upsert by (school, client_offline_id) and never touch a pk lookup — so a
        # box-local pk can never collide with a different operator record. The split is
        # SHARED with the box-side inbox (apps.sync_engine.edge_inbox.split_bundle_rows) so
        # the two receivers cannot drift on what a row means.
        from apps.sync_engine.edge_inbox import split_bundle_rows

        update_rows, insert_rows, delete_rows, malformed = split_bundle_rows(rows)

        # sync_origin="edge-push": record provenance so a later cloud->box PULL to the
        # same box does not echo the rows it just pushed up back down to it.
        out = apply_changes(
            str(school.id), request.user, update_rows, persist_conflicts=True, sync_origin="edge-push"
        )
        inserted = (
            apply_edge_inserts(str(school.id), request.user, insert_rows, sync_origin="edge-push")
            if insert_rows
            else {"created": 0, "updated": 0, "results": []}
        )
        # Deletions LAST, so a window containing both an edit and a later deletion of the
        # same row ends in the state the sender actually holds.
        removed = (
            apply_deletes(str(school.id), request.user, delete_rows, sync_origin="edge-push")
            if delete_rows
            else {"deleted": 0, "results": []}
        )
        try:
            from apps.sync_engine.sync_status import record_observed_cycle

            record_observed_cycle(
                school,
                ok=True,
                pushed=len(rows),
                conflicts=len(out["conflicts"]),
                created=int(inserted["created"] or 0),
                upserted=int(inserted["updated"] or 0),
                message="inbound edge-push applied",
            )
        except Exception:  # noqa: BLE001 — observability must never fail the upload
            pass
        # A box pushing UP is not blocked by skew: the cloud has every column the box
        # could possibly send. But if the CLOUD is the one behind, the box's rows carry
        # columns this schema lacks and degrade per row - so the skew is reported back
        # rather than left to look like unexplained refusals.
        _withheld, advice = _schema_handshake(request)
        payload_advice = {"schema_advice": advice} if advice else {}
        return Response(
            {
                **payload_advice,
                "ok": True,
                "received": len(rows),
                "malformed": malformed,
                "applied": out["success_count"],
                "conflicts": len(out["conflicts"]),
                "created": inserted["created"],
                "upserted": inserted["updated"],
                "deleted": removed["deleted"],
                "results": out["results"],
                "conflict_details": out["conflicts"],
                "insert_results": inserted["results"],
                "delete_results": removed["results"],
            }
        )


@extend_schema_view(
    get=extend_schema(
        tags=["Offline Sync"],
        summary="Download signed sync bundle (cloud->box pull)",
        description=(
            "The sovereign edge box PULLS the tenant's rows changed since its cursor. "
            "Query params: `since` (ISO-8601 high-water; omit for a full snapshot) and "
            "`entities` (comma-separated filter). Returns a signed NDJSON delta bundle — "
            "the SAME wire format the box uploads — with the new high-water in the "
            "`X-RMC-Sync-High-Water` response header so the box can advance its pull "
            "cursor. Echo-suppressed: rows the operator itself received from this box's "
            "push are not shipped back."
        ),
        responses={200: bytes, 400: dict, 403: dict},
    ),
)
class SyncBundleDownloadView(APIView):
    """Cloud->box delta PULL. The missing half of the edge sync loop.

    Edge-initiated (the box calls OUT, so the operator never reaches into a private
    LAN), authenticated by the same edge machine credential as the upload receiver.
    Reuses ``build_edge_delta_bundle`` — the exact delta+signing the box uses to push —
    run on the operator to serve the box.
    """

    authentication_classes = [EdgeCredentialAuthentication, *api_settings.DEFAULT_AUTHENTICATION_CLASSES]
    permission_classes = [IsAuthenticated]
    # Defaults FIRST so `Accept: */*` still resolves to JSON for the error branches;
    # the bundle renderer only wins on the box's explicit Accept. Without it here,
    # negotiation 406s before get() is entered. See SyncBundleRenderer.
    renderer_classes = [*api_settings.DEFAULT_RENDERER_CLASSES, SyncBundleRenderer]

    def get(self, request):
        school = getattr(request, "school", None)
        if school is None:
            return Response({"ok": False, "error": "school_required"}, status=403)
        if not user_may_operate_on_school(request, school):
            return Response({"ok": False, "error": "forbidden"}, status=403)

        raw_since = (request.query_params.get("since") or "").strip()
        since = None
        if raw_since:
            since = parse_datetime(raw_since)
            if since is None:
                return Response(
                    {"ok": False, "error": "invalid_since", "detail": "use ISO-8601"}, status=400
                )
            if timezone.is_naive(since):
                since = timezone.make_aware(since, timezone.get_current_timezone())

        entities = [
            e.strip().lower()
            for e in (request.query_params.get("entities") or "").split(",")
            if e.strip()
        ]

        # G4 schema handshake. Withhold ONLY what this box's schema cannot accept, and
        # say which and why — instead of shipping rows that die per-row on a column the
        # box does not have, which reads to an operator as an unexplained "12 NOT applied".
        withheld, advice = _schema_handshake(request)
        if withheld:
            from apps.api.sync_services import _get_entity_config

            servable = set(entities) if entities else set(_get_entity_config(include_derived=True))
            entities = sorted(servable - withheld)
            if not entities:
                # Everything this box asked for is incompatible. An EMPTY entity list means
                # "all" to the builder, so it has to be short-circuited here or the guard
                # would invert into shipping the whole corpus.
                resp = HttpResponse(b"", content_type=BUNDLE_CONTENT_TYPE)
                resp[SYNC_ROW_COUNT_HEADER] = "0"
                resp[SYNC_SCHEMA_ADVICE_HEADER] = advice or "schema skew: nothing servable"
                resp[SYNC_WITHHELD_HEADER] = ",".join(sorted(withheld))
                # This is the branch where the box needs the upgrade MOST — it can accept
                # nothing at all until it migrates — so the target must be stamped here
                # too, not only on the success path below.
                _stamp_manifest_handshake(resp, request, school)
                return resp
        try:
            data, meta = build_edge_delta_bundle(
                school, since=since, entities=entities, device_id="cloud"
            )
        except ValueError as exc:  # unknown_entities:[...]
            return Response({"ok": False, "error": str(exc)}, status=400)

        resp = HttpResponse(data, content_type=BUNDLE_CONTENT_TYPE)
        if meta.get("high_water_iso"):
            resp[SYNC_HIGH_WATER_HEADER] = meta["high_water_iso"]
        resp[SYNC_ROW_COUNT_HEADER] = str(meta.get("row_count", 0))
        if withheld:
            # The box needs BOTH: the human sentence for the Sync Center, and the machine
            # list so it can report exactly which entities are frozen until it migrates.
            resp[SYNC_SCHEMA_ADVICE_HEADER] = advice
            resp[SYNC_WITHHELD_HEADER] = ",".join(sorted(withheld))

        # G8 parity seal. Answered on the same response for the same NAT reason as the
        # directive: this is the only moment the cloud can tell the box anything.
        try:
            drifted, parity_advice = _parity_handshake(request, school, withheld=withheld)
            if drifted:
                resp[SYNC_PARITY_DRIFT_HEADER] = ",".join(drifted)
                if parity_advice:
                    resp[SYNC_PARITY_ADVICE_HEADER] = parity_advice
        except Exception:  # noqa: BLE001 — the bundle is the payload; parity is a bonus
            pass
        # OTA manifest handshake, on the response the box was already collecting. This is
        # the whole "no second channel" property: an upgrade is ANNOUNCED on the data
        # rail, and only the bytes travel on the upgrade routes.
        _stamp_manifest_handshake(resp, request, school)

        # The box is behind NAT, so this response is the only moment the cloud can hand it
        # an instruction. Best-effort: a directive failure must never cost the box its data.
        directive_kind = ""
        try:
            from apps.sync_engine.models import claim_pending_directive

            directive = claim_pending_directive(school)
            if directive is not None:
                resp[SYNC_DIRECTIVE_HEADER] = directive.kind
                directive_kind = directive.kind
        except Exception:  # noqa: BLE001 — the bundle is the payload; a directive is a bonus
            pass

        # EVERY served bundle is a real cloud<->box transfer, so every one is
        # recorded. This used to sit inside the directive branch, which meant an
        # ordinary pull -- a box polling with nothing to push, the overwhelmingly
        # common case -- recorded nothing at all. A healthy box was therefore
        # invisible on the Sync Center, which kept showing whatever last went
        # wrong until something else happened to write a row.
        try:
            from apps.sync_engine.sync_status import record_observed_cycle

            record_observed_cycle(
                school,
                ok=True,
                pulled=int(meta.get("row_count") or 0),
                message=(
                    f"bundle served to box; directive served: {directive_kind}"
                    if directive_kind
                    else "bundle served to box"
                ),
            )
        except Exception:  # noqa: BLE001 — observability must never cost the box its data
            pass
        return resp


__all__ = ["SyncBundleUploadView", "SyncBundleDownloadView"]
