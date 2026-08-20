"""Edge outbox core — build delta bundles + mint/resolve the edge machine credential.

Shared by the export/mint/post management commands and the receiver's credential
auth (Tier 3 Slices 2-3). The edge machine credential reuses the existing
``accounts.OfflineCapabilityToken`` (sha256-fingerprinted, revocable via both the
token and its ``DeviceRegistration``, with an expiry) tagged with ``EDGE_SYNC_SCOPE``
so an ordinary mobile offline token can never be used to drive server->server sync.
No new model / migration — a sovereign box registers as a device.

Direction is edge-initiated / outbound-only: the box POSTs its bundle UP to the
operator; the operator never needs to reach a box behind a private LAN.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone as _dt_timezone

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.sync_engine.gateway_retry import call_with_gateway_retry

logger = logging.getLogger(__name__)

BUNDLE_CONTENT_TYPE = "application/x-rmc-sync-bundle+ndjson"

# Sentinel that sorts before every real timestamp, for rows whose updated_at is null.
_EPOCH = datetime.min.replace(tzinfo=_dt_timezone.utc)


def _parse_iso(value):
    """ISO string -> aware datetime, or ``None``. Used to give a tombstone row the same
    real-datetime sort key every other row gets - sorting the ISO STRING would only be
    chronological while every row shared one UTC offset, and a mis-ordered page boundary
    is a mis-placed cursor."""
    from django.utils.dateparse import parse_datetime

    if not value:
        return None
    parsed = parse_datetime(value) if isinstance(value, str) else value
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed

# Marker stamped into an edge credential's permission_bitmap. resolve_edge_credential
# REQUIRES it, so a plain offline capability token can't authenticate the sync POST.
EDGE_SYNC_SCOPE = "edge-sync-machine"


# --------------------------------------------------------------------------- #
# Bundle building (shared by export_edge_delta_bundle + post_edge_outbox)
# --------------------------------------------------------------------------- #
def build_edge_delta_rows(school, *, since=None, entities=None):
    """The school's changed ROWS since ``since``, plus meta — unsigned and unpackaged.

    Split out of :func:`build_edge_delta_bundle` so a caller that must PAGE the work can
    sign each page separately. The receiver caps a single bundle at
    ``RMC_SYNC_BUNDLE_MAX_ROWS`` and rejects an oversized one WHOLE, so a box with a
    real backlog has to send several bundles — which is impossible if the only entry
    point hands back pre-signed bytes.

    Returns ``(rows, meta)`` with ``meta = {"counts", "row_count", "high_water_iso",
    "high_water"}``. Rows are sorted by ``updated_at`` ACROSS entities so that a caller
    paging them can treat the last row of a page as a safe global cursor: everything
    older has already been sent. (The per-entity grouping the builder scans in is not a
    safe paging order — truncating it would strand older rows in later entities behind
    an advanced cursor.)
    """
    from apps.api.sync_services import _get_entity_config  # SOT: (model, allowed fields)
    from apps.sync_engine.models import _MISSING, sync_echo_updated_at_map

    # Building a delta bundle is always an EDGE sync operation (box push / operator
    # serving a pull), so it uses the full two-way registry.
    config = _get_entity_config(include_derived=True)
    want = {str(e).strip().lower() for e in (entities or []) if str(e).strip()}
    unknown = want - set(config)
    if unknown:
        raise ValueError(f"unknown_entities:{sorted(unknown)}")

    rows: list[dict] = []
    sort_keys: list = []
    counts: dict[str, int] = {}
    high_water = None
    for entity_type, (model, allowed) in config.items():
        if want and entity_type not in want:
            continue
        qs = model._default_manager.filter(school=school)  # school= is the tenant-isolation kwarg
        if since is not None:
            qs = qs.filter(updated_at__gt=since)
        # Echo-suppression: a row whose current updated_at still equals what SYNC last
        # wrote (recorded in the ledger) is a pure echo of an inbound apply — skip it so
        # a pulled/pushed row never ping-pongs back. A later LOCAL edit moves updated_at
        # off the recorded value, so genuine changes still ship. See SyncApplyLedger.
        echo = sync_echo_updated_at_map(school, entity_type)
        n = 0
        for instance in qs.order_by("updated_at").iterator():
            updated_at = getattr(instance, "updated_at", None)
            # Advance the cursor over EVERY scanned row, including an echo we are about to
            # skip. Otherwise, when the newest row in the window is a pure echo, high_water
            # never reaches its timestamp, the cursor never advances past it, and every
            # cycle re-scans and re-suppresses the same window (bounded churn, wasted work).
            # A later GENUINE edit still ships: it gets a strictly greater updated_at.
            if updated_at and (high_water is None or updated_at > high_water):
                high_water = updated_at
            applied = echo.get(str(instance.pk), _MISSING)
            if applied is not _MISSING and applied == updated_at:
                continue  # unchanged since sync wrote it → echo
            changes = {f: getattr(instance, f) for f in sorted(allowed) if hasattr(instance, f)}
            rows.append(
                {
                    "entity_type": entity_type,
                    "id": instance.pk,
                    # Non-empty only for records created offline on this box; the operator
                    # upserts those by (school, client_offline_id) instead of by pk.
                    "client_offline_id": getattr(instance, "client_offline_id", "") or "",
                    "changes": changes,
                    "updated_at": updated_at.isoformat() if updated_at else None,
                }
            )
            # Sort key kept alongside as a real datetime, then stripped below. Sorting the
            # ISO STRING would only be chronological while every row shares one UTC offset,
            # and a mis-ordered page boundary is a mis-placed cursor — i.e. skipped rows.
            sort_keys.append(updated_at)
            n += 1
        if n:
            counts[entity_type] = n

    # DELETIONS ride the same rail. A tombstone becomes an ordinary row carrying
    # ``op="delete"`` and using ``deleted_at`` as its ``updated_at``, so it sorts into the
    # same global chronological order as everything else and a page boundary stays a valid
    # cursor position. Emitting them here rather than through a channel of their own is
    # what makes deletion inherit - for free - the paging, signing, cursor, directive and
    # replay machinery the row rail already has. See apps.sync_engine.tombstones.
    from apps.sync_engine.tombstones import DELETE_OP, iter_tombstone_rows

    tomb_rows, tomb_high_water = iter_tombstone_rows(school, since=since, entities=entities)
    for row in tomb_rows:
        rows.append(row)
        sort_keys.append(row["updated_at"] and _parse_iso(row["updated_at"]))
        counts[f"{row['entity_type']}:{DELETE_OP}"] = (
            counts.get(f"{row['entity_type']}:{DELETE_OP}", 0) + 1
        )
    if tomb_high_water is not None and (high_water is None or tomb_high_water > high_water):
        high_water = tomb_high_water

    # Global updated_at order so a page boundary is a valid cursor position: everything
    # older than the last row of a page has, by construction, already been sent. The
    # per-entity scan order the builder walks in is NOT safe to page — truncating it would
    # strand older rows of later entities behind an advanced cursor.
    #
    # Rows with a null updated_at sort FIRST: they carry no position at all, so they must
    # ship before any cursor moves past them rather than being stranded after it.
    from apps.api.sync_services import enrich_delta_rows_with_fk_referents

    rows = enrich_delta_rows_with_fk_referents(rows, school, config)
    sort_keys = []
    for row in rows:
        raw = row.get("updated_at")
        if not raw:
            sort_keys.append(None)
            continue
        parsed = parse_datetime(str(raw))
        if parsed is None:
            sort_keys.append(None)
            continue
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        sort_keys.append(parsed)
    order = sorted(
        range(len(rows)),
        key=lambda i: (sort_keys[i] is not None, sort_keys[i] or _EPOCH),
    )
    rows = [rows[i] for i in order]
    meta = {
        "counts": counts,
        "row_count": len(rows),
        "high_water_iso": high_water.isoformat() if high_water else None,
        "high_water": high_water,
    }
    return rows, meta


def build_edge_delta_bundle(school, *, since=None, entities=None, device_id="edge"):
    """Package the school's records changed since ``since`` into a signed delta bundle.

    Returns ``(bundle_bytes, meta)`` where ``meta`` is
    ``{"counts", "row_count", "high_water_iso"}``. UPDATE-only rows for the
    ``apply_changes`` entity set (identity holds because the clone is pk-preserving).
    Raises ``ValueError('unknown_entities:...')`` for an unknown entity filter.
    """
    from apps.sync_engine.delta_bundle import export_delta_bundle

    rows, meta = build_edge_delta_rows(school, since=since, entities=entities)
    data = export_delta_bundle(school_id=str(school.id), rows=rows, device_id=device_id or "edge")
    return data, meta


# --------------------------------------------------------------------------- #
# Machine credential (mint on the operator, resolve on the receiver)
# --------------------------------------------------------------------------- #
def _fingerprint(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def mint_edge_credential(school, user, *, device_id="", days=365, public_key_fingerprint=""):
    """Register the box as a device + mint a long-lived edge machine credential.

    Returns ``(raw_token, token_obj)``. The raw token is shown ONCE; only its sha256
    is persisted. Refuses to re-mint for a REVOKED device (reinstatement must be an
    explicit operator action), mirroring OfflineTokenMintView's online-boundary rule.
    """
    from apps.accounts.models_offline_device import DeviceRegistration, OfflineCapabilityToken

    device_id = (device_id or f"edge-{getattr(school, 'slug', '') or school.pk}").strip()[:128]
    if DeviceRegistration.objects.filter(
        school=school, user=user, device_id=device_id, revoked_at__isnull=False
    ).exists():
        raise ValueError("device_revoked")

    device, _created = DeviceRegistration.objects.update_or_create(
        school=school,
        user=user,
        device_id=device_id,
        defaults={
            "public_key_fingerprint": public_key_fingerprint or "",
            "permission_bitmap": [EDGE_SYNC_SCOPE],
            "last_seen_at": timezone.now(),
        },
    )
    raw_token = secrets.token_urlsafe(32)
    token = OfflineCapabilityToken.objects.create(
        device=device,
        school=school,
        user=user,
        token_fingerprint=_fingerprint(raw_token),
        permission_bitmap=[EDGE_SYNC_SCOPE],
        expires_at=timezone.now() + timedelta(days=max(1, int(days))),
    )
    return raw_token, token


def resolve_edge_credential(raw_token: str):
    """Resolve a raw edge bearer token to ``(user, school)``, or ``None`` if invalid.

    Requires the ``EDGE_SYNC_SCOPE`` marker, a non-revoked non-expired token, and a
    non-revoked device. Touches ``last_seen_at`` on success. Never raises — an
    unrecognised/expired/revoked token simply resolves to ``None``.
    """
    from apps.accounts.models_offline_device import OfflineCapabilityToken

    if not raw_token:
        return None
    token = (
        OfflineCapabilityToken.objects.select_related("device", "school", "user")
        # tenant-isolation-allow: credential-resolution-is-intentionally-cross-tenant-the-sha256-fingerprint-resolves-which-school
        .filter(token_fingerprint=_fingerprint(raw_token))
        .first()
    )
    if token is None or not token.is_valid:
        return None
    if EDGE_SYNC_SCOPE not in (token.permission_bitmap or []):
        return None
    device = token.device
    if device is not None and device.revoked_at is not None:
        return None
    if device is not None:
        device.touch_seen()
    return token.user, token.school


# --------------------------------------------------------------------------- #
# Transport (box side) — POST a bundle to the operator receiver
# --------------------------------------------------------------------------- #
def local_schema_head_header() -> str:
    """This deployment's per-app migration heads, encoded for the handshake header.

    Only the apps that OWN synced entities, so the header stays short and says exactly
    what the far side needs in order to decide what it may safely send.
    """
    try:
        from apps.api.sync_services import entity_app_labels
        from apps.sync_engine.schema_guard import encode_heads, local_migration_heads

        return encode_heads(local_migration_heads(set(entity_app_labels().values())))
    except Exception:  # noqa: BLE001 - the handshake is advisory; never break transport
        return ""


def post_bundle(endpoint: str, token: str, data: bytes, *, timeout: float = 30.0):
    """POST a signed bundle to the operator's receiver with a bearer credential.

    Returns ``(status_code, body_dict)``. A 4xx/5xx is a real HTTP RESPONSE (returned,
    not raised) so the caller can distinguish "operator rejected the bundle" from
    "couldn't reach the operator". A connectivity failure (``URLError``/``OSError``,
    e.g. offline) PROPAGATES — the caller queues the bundle and retries later.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": BUNDLE_CONTENT_TYPE,
    }
    schema_head = local_schema_head_header()
    if schema_head:
        headers[SYNC_SCHEMA_HEAD_HEADER] = schema_head
    def _attempt():
        req = urllib.request.Request(endpoint, data=data, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator URL, not user input
                return resp.getcode(), resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:  # a response with a 4xx/5xx status, not a connectivity failure
            try:
                return exc.code, exc.read().decode("utf-8", "replace")
            except (OSError, AttributeError):
                return exc.code, ""

    # A 502/503/504 here is the cloud's PROXY answering while its application did not,
    # and the commonest cause is simply that the service is cold — measured recovering
    # inside a minute. Without this retry a box on a cadence records a failed push for a
    # cloud that is merely waking up, and the operator, whose own browser warmed it,
    # sees a healthy site and no explanation. 4xx is untouched: that is a decision the
    # cloud made and must surface immediately.
    status, body = call_with_gateway_retry(
        _attempt,
        on_retry=lambda attempt, total, wait: logger.info(
            "edge push hit HTTP gateway error; retry %s/%s in %.0fs", attempt + 1, total, wait
        ),
    )
    try:
        parsed = json.loads(body) if body else {}
    except ValueError:
        parsed = {"raw": body}
    return status, parsed


# High-water response header the DOWNLOAD endpoint stamps so the box can advance its
# pull cursor without re-parsing the bundle body. Row-count is informational.
SYNC_HIGH_WATER_HEADER = "X-RMC-Sync-High-Water"
SYNC_ROW_COUNT_HEADER = "X-RMC-Sync-Row-Count"
# Schema handshake (G4). The box states which migration each synced app is on; the cloud
# answers with what it withheld and why. Both are advisory headers rather than a
# negotiation round trip, so the handshake costs no extra request.
SYNC_SCHEMA_HEAD_HEADER = "X-RMC-Sync-Schema-Head"
SYNC_SCHEMA_ADVICE_HEADER = "X-RMC-Sync-Schema-Advice"
SYNC_WITHHELD_HEADER = "X-RMC-Sync-Withheld-Entities"
# Cloud->box instruction channel. The cloud cannot reach a box behind NAT, so an operator
# request (currently only "full-resync") rides back on the box's own next download.
SYNC_DIRECTIVE_HEADER = "X-RMC-Sync-Directive"


def pull_bundle(
    endpoint: str,
    token: str,
    *,
    since=None,
    entities=None,
    timeout: float = 30.0,
    collect: dict | None = None,
):
    """GET a signed delta bundle DOWN from the operator (cloud->box pull, box side).

    The mirror of :func:`post_bundle`: the box calls OUT to the operator's download
    endpoint with its machine credential and an optional ``since`` cursor, and the
    operator streams back the bundle of rows changed since then. Returns
    ``(status_code, body_bytes, high_water_iso)`` where ``high_water_iso`` is read from
    the response header (``None`` if absent). A 4xx/5xx is a real HTTP RESPONSE
    (returned, not raised) so the caller can tell "operator rejected" from "couldn't
    reach the operator"; a connectivity failure (``URLError``/``OSError``, e.g. offline)
    PROPAGATES so the caller leaves its cursor put and retries later.

    Pass ``collect=`` a mutable dict to also receive out-of-band response metadata (the
    cloud->box directive). Kept out of the return tuple so existing 3-tuple callers —
    including the tested pull command — are untouched.
    """
    from urllib.parse import urlencode

    query = {}
    if since:
        query["since"] = since if isinstance(since, str) else since.isoformat()
    ents = [str(e).strip().lower() for e in (entities or []) if str(e).strip()]
    if ents:
        query["entities"] = ",".join(ents)
    url = endpoint + (("?" + urlencode(query)) if query else "")

    headers = {"Authorization": f"Bearer {token}", "Accept": BUNDLE_CONTENT_TYPE}
    # Tell the cloud which schema this box is on, so it can withhold the entities this
    # box could not apply anyway INSTEAD of shipping rows that die per-row with no
    # explanation. Advisory: a cloud that predates the handshake simply ignores it.
    schema_head = local_schema_head_header()
    if schema_head:
        headers[SYNC_SCHEMA_HEAD_HEADER] = schema_head
    req = urllib.request.Request(url, method="GET", headers=headers)
    high_water = None
    directive = None
    advice = None
    withheld = None

    def _read_meta(source):
        nonlocal advice, withheld
        if not source:
            return
        advice = source.get(SYNC_SCHEMA_ADVICE_HEADER)
        withheld = source.get(SYNC_WITHHELD_HEADER)

    def _attempt():
        nonlocal high_water, directive
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator URL, not user input
                high_water = resp.headers.get(SYNC_HIGH_WATER_HEADER)
                directive = resp.headers.get(SYNC_DIRECTIVE_HEADER)
                _read_meta(resp.headers)
                return resp.getcode(), resp.read()
        except urllib.error.HTTPError as exc:  # a response with a 4xx/5xx status, not a connectivity failure
            try:
                high_water = exc.headers.get(SYNC_HIGH_WATER_HEADER) if exc.headers else None
                directive = exc.headers.get(SYNC_DIRECTIVE_HEADER) if exc.headers else None
                _read_meta(exc.headers)
                return exc.code, exc.read()
            except (OSError, AttributeError):
                return exc.code, b""

    # Same reasoning as the push path: a cold cloud 502s every route, including static
    # files, and recovers within a minute. Pulling is the data path, so a spurious
    # failure here costs the box a whole interval of convergence.
    status, body = call_with_gateway_retry(
        _attempt,
        on_retry=lambda attempt, total, wait: logger.info(
            "edge pull hit HTTP gateway error; retry %s/%s in %.0fs", attempt + 1, total, wait
        ),
    )
    if collect is not None:
        collect["directive"] = (directive or "").strip()
        collect["schema_advice"] = (advice or "").strip()
        collect["withheld_entities"] = [
            e.strip() for e in (withheld or "").split(",") if e.strip()
        ]
    return status, body, high_water


def wait_for_changes(endpoint: str, token: str, *, since=None, wait: int = 25,
                     timeout: float = 40.0):
    """Hold one request open until the cloud has something for this box (G6).

    Returns ``(status_code, payload_dict)``. ``payload["changed"]`` is the answer;
    ``payload["supported"]`` is ``False`` when the cloud does not run the feed, which the
    caller must treat as "fall back to the cadence" rather than as an error.

    ``timeout`` is deliberately LONGER than ``wait``: the cloud intends to hold the
    request for ``wait`` seconds, so a client timeout at or below that would abort every
    hold at the moment it was about to answer, and read as a connectivity failure on a
    perfectly healthy link.

    A connectivity failure PROPAGATES, exactly as in :func:`pull_bundle`, so the caller
    can tell "nothing to do" from "cannot reach the cloud" and back off accordingly.
    """
    from urllib.parse import urlencode

    query = {"wait": int(max(0, wait))}
    if since:
        query["since"] = since if isinstance(since, str) else since.isoformat()
    url = endpoint + "?" + urlencode(query)
    req = urllib.request.Request(
        url, method="GET", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator URL, not user input
            status = resp.getcode()
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            body = exc.read().decode("utf-8", "replace")
        except (OSError, AttributeError):
            body = ""
    try:
        parsed = json.loads(body) if body else {}
    except ValueError:
        parsed = {"raw": body}
    return status, parsed


__all__ = [
    "EDGE_SYNC_SCOPE",
    "BUNDLE_CONTENT_TYPE",
    "SYNC_HIGH_WATER_HEADER",
    "SYNC_ROW_COUNT_HEADER",
    "SYNC_DIRECTIVE_HEADER",
    "SYNC_SCHEMA_HEAD_HEADER",
    "SYNC_SCHEMA_ADVICE_HEADER",
    "SYNC_WITHHELD_HEADER",
    "local_schema_head_header",
    "wait_for_changes",
    "build_edge_delta_rows",
    "build_edge_delta_bundle",
    "mint_edge_credential",
    "resolve_edge_credential",
    "post_bundle",
    "pull_bundle",
]
