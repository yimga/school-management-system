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
    SYNC_ROW_COUNT_HEADER,
    SYNC_SCHEMA_ADVICE_HEADER,
    SYNC_SCHEMA_HEAD_HEADER,
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
