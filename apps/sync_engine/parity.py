"""G8: prove the two sides HOLD the same rows, not merely that the protocol would converge.

WHAT WAS MISSING. Every other guarantee in this engine is about the JOURNEY. The cursor
is honest, the bundle is signed, a replay is refused, a delete does not come back, and
``convergence_harness`` proves the protocol converges by driving real bundles through the
real apply path. But it drives ONE database against a modelled ``Mirror``, and says so in
its own docstring. Nothing anywhere ever asked the other side what it actually holds. So
a row that went missing for a reason the protocol does not model - a restore from an old
dump, a hand-run ``DELETE`` on the box, an apply that failed silently on a schema the
handshake had not yet learned to withhold - stayed missing forever, because an
incremental delta only ever offers what changed SINCE the cursor, and a row that is
absent has no ``updated_at`` to be greater than anything.

This module closes that: the box asks "here is my digest per entity - does yours agree?"
and the cloud answers with the entities that differ.

WHY NOT ``updated_at``, WHICH IS THE OBVIOUS THING TO HASH. It is wrong, and quietly so.
``updated_at`` is ``auto_now``: when the box applies a row the cloud sent, the local save
stamps a NEW timestamp. Two perfectly converged sides therefore hold different
``updated_at`` for the same row, permanently. A digest over it would report drift on
every row of every entity on the first cycle and never stop - the worst kind of
monitoring, the kind everyone learns to ignore. Echo-suppression exists precisely because
this skew is normal (see ``SyncApplyLedger``).

So the digest is taken over the RAIL FIELDS - the same ``allowed`` set
``build_edge_delta_rows`` ships. That is exactly the set the two sides are supposed to
agree on, and nothing else. A column that never crosses the rail (a local cache, a
box-only counter) is not parity, and a digest that flagged it would be lying.

WHY NOT "hash the whole database", which is what every replication write-up suggests.
The two deployments do not have the same database. The cloud runs schema-per-tenant
(``USE_DJANGO_TENANTS=1``); a sovereign box runs shared-DB + RLS with ``SINGLE_TENANT``.
Table sets, sequences, ``django_migrations`` and pk sequences all differ legitimately. The
only thing that is supposed to be identical is the tenant's rail data for one school, so
that is the only thing worth hashing. Scoping is by the same ``school=`` kwarg the delta
builder uses, which is what makes this identical code on two different topologies.

IDENTITY, AND WHY IT IS CONDITIONAL. ``client_offline_id`` when it is non-empty,
otherwise the pk:

  * a row created on the CLOUD is pushed down by ``_create_from_cloud_pull``, which
    PRESERVES the operator's pk - so pk agrees on both sides and the anchor is empty;
  * a row created on the BOX is upserted by ``(school, client_offline_id)`` in
    ``apply_edge_inserts``, and the cloud mints its OWN pk - so the pks differ by
    construction and only the anchor agrees.

Keying on pk alone would report every offline-created row as drift forever. Keying on the
anchor alone would collapse every cloud-authored row onto one empty key.

WHY XOR-FOLD PLUS A COUNT. Folding per-row digests with XOR makes the entity digest
order-independent, so both sides can stream rows in whatever order their planner likes
with no ``ORDER BY`` and no sort buffer - this has to be cheap enough to run on a mini-PC
without disturbing the cycle. XOR's known weakness is that a duplicated element cancels
itself; identities are unique per entity so duplicates cannot arise, and the row COUNT
travels alongside anyway, which catches any cancellation and is also the cheapest possible
first-line signal.

WHY THE HEADER IS TRUNCATED to 64 bits per entity. It is a health signal on a channel
that is already HMAC-signed, bearer-authenticated and TLS-wrapped - not a security
boundary. 64 bits plus an exact row count is far past what an accidental divergence will
slip through, and it keeps ~40 entities inside one ordinary header instead of forcing a
second request.

WHAT THE REPAIR IS. Per-entity, because the cursor is per (school, direction) and
rewinding it would replay the entire corpus to fix one table. A drifted entity is
re-pulled on its own with ``since=None`` - the existing download endpoint already takes
``entities=`` - so the flush rides the same rail, the same signature and the same
idempotent apply as everything else, and touches nothing but the entity that drifted.

NEVER RAISES, ANYWHERE. This is a diagnostic, and a diagnostic that can break a sync
cycle is worse than no diagnostic at all - the same rule ``schema_guard`` follows. Every
public function here answers with an empty/neutral value on any failure.
"""
from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import hashlib
import json
import logging
import uuid as _uuid

logger = logging.getLogger(__name__)

#: Bytes in a sha256 digest - the width the XOR fold works over.
_DIGEST_BYTES = 32
#: Hex characters kept per entity when the digest travels in a header. See the module
#: docstring: a health signal on an authenticated channel, paired with an exact count.
_HEADER_HEX = 16  # magic-number-allow: truncated parity digest width (hex chars)
#: Field separator inside a row's canonical pre-image. A unit separator cannot occur in
#: the JSON that follows it, so no identity can be confused with a value.
_SEP = "\x1f"

#: Default gap between parity sweeps. See :func:`interval_seconds` for why it is an hour
#: rather than every cycle.
_DEFAULT_INTERVAL_SECONDS = 3600  # magic-number-allow: default parity sweep gap (1h, seconds)
#: Floor an operator may pin the sweep interval to. A sweep is a full scan; letting it be
#: pinned to seconds would let one setting turn the cycle into a continuous table walk.
_MIN_INTERVAL_SECONDS = 60

_CACHE_KEY = "rmc:sync_engine:parity:last:%s"


def _cache():
    from django.core.cache import cache

    return cache


def enabled() -> bool:
    """Master switch. Off => the box sends no digest and the cloud answers none."""
    try:
        from django.conf import settings

        return bool(getattr(settings, "RMC_SYNC_PARITY_ENABLED", True))
    except Exception:  # noqa: BLE001 - a settings read must never break a cycle
        return False


def interval_seconds() -> int:
    """How often a box may spend a full-corpus scan on parity.

    Parity is a SWEEP: it reads every row of every entity, unlike the delta the cycle
    normally builds. Running it on every tick would turn a 20-second cadence into a
    continuous table scan on hardware chosen for being small and silent. Hourly is far
    more often than the failures this catches actually occur, and a drifted entity that
    waits at most an hour to be noticed has usually been drifted for days.
    """
    try:
        from django.conf import settings

        return max(
            _MIN_INTERVAL_SECONDS,
            int(getattr(settings, "RMC_SYNC_PARITY_INTERVAL_SECONDS", _DEFAULT_INTERVAL_SECONDS)),
        )
    except Exception:  # noqa: BLE001
        return _DEFAULT_INTERVAL_SECONDS


def max_flush_entities() -> int:
    """Cap on entities auto-flushed in ONE cycle.

    A box that has genuinely lost its database will report every entity as drifted, and
    flushing all of them at once is a full corpus re-pull dressed up as a repair - on a
    link the school may be paying for by the megabyte. Above the cap the cycle repairs
    the worst few and SAYS so, which is the honest report; the rest follow on later
    cycles, or an operator issues a real full-resync directive, which is the right tool
    for a box that has lost everything.
    """
    try:
        from django.conf import settings

        return max(1, int(getattr(settings, "RMC_SYNC_PARITY_MAX_FLUSH_ENTITIES", 3)))
    except Exception:  # noqa: BLE001
        return 3


# --------------------------------------------------------------------------- #
# Canonical value encoding
# --------------------------------------------------------------------------- #
def _canonical(value):
    """One stable representation for a column value, on either deployment.

    Both sides run this exact function, so the bar is DETERMINISM, not any particular
    format. The cases that are spelled out are the ones where two Postgres deployments
    could otherwise disagree on the Python object they hand back:

      * datetimes are normalised to UTC before formatting, so a box configured on a local
        ``TIME_ZONE`` and a cloud on UTC digest the same instant identically;
      * ``Decimal`` is normalised then formatted non-scientifically, so ``1.50``,
        ``1.5`` and ``1.5E+0`` - all legal readings of the same money value - cannot
        produce three different digests;
      * ``memoryview`` is what psycopg hands back for ``bytea``, and its ``str()`` embeds
        the object's ADDRESS, which would differ on every single call.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return repr(value)  # deterministic shortest round-trip in Python 3
    if isinstance(value, _decimal.Decimal):
        if value.is_nan() or value.is_infinite():
            return str(value)
        return format(value.normalize(), "f")
    if isinstance(value, _dt.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(_dt.timezone.utc)
        return value.isoformat()
    if isinstance(value, (_dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, _dt.timedelta):
        return str(value.total_seconds())
    if isinstance(value, _uuid.UUID):
        return str(value)
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return hashlib.sha256(bytes(value)).hexdigest()
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, dict):
        return {
            str(k): _canonical(v)
            for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    return str(value)


def _row_digest(identity: str, values: dict) -> bytes:
    payload = json.dumps(
        {k: _canonical(v) for k, v in values.items()},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(f"{identity}{_SEP}{payload}".encode("utf-8")).digest()


def _concrete_names(model) -> set:
    names = set()
    for f in model._meta.get_fields():
        if not getattr(f, "concrete", False):
            continue
        if getattr(f, "many_to_many", False):
            continue
        if getattr(f, "name", ""):
            names.add(f.name)
        att = getattr(f, "attname", "")
        if att:
            names.add(att)
    return names


def _hashable_field_names(model, allowed) -> list:
    """``allowed`` intersected with the columns this deployment's model ACTUALLY has.

    ``.values()`` raises ``FieldError`` for one unknown name and takes the whole entity
    with it, whereas the delta builder skips a missing attribute per row. A box mid-way
    through a migration is exactly when parity is most worth having, so the narrower set
    is used rather than losing the entity.
    """
    known = _concrete_names(model)
    return sorted(n for n in allowed if n in known)


# --------------------------------------------------------------------------- #
# Digests
# --------------------------------------------------------------------------- #
def entity_digest(school, entity_type, model, allowed) -> dict:
    """``{"n": <rows>, "h": "<64 hex>"}`` for one entity of one school.

    Streamed through ``.values()`` rather than model instances: this walks the whole
    entity, and instantiating every row (plus a FK query per relation from ``getattr``)
    is the difference between a scan a mini-PC does not notice and one an operator does.
    """
    fields = _hashable_field_names(model, allowed)
    pk_name = model._meta.pk.attname
    anchor = "client_offline_id" if "client_offline_id" in _concrete_names(model) else ""

    columns = [pk_name] + ([anchor] if anchor else []) + fields
    fold = bytearray(_DIGEST_BYTES)
    n = 0
    qs = model._default_manager.filter(school=school)  # school= is the tenant-isolation kwarg
    for row in qs.values(*columns).iterator():
        identity = str(row.get(anchor) or "").strip() if anchor else ""
        if not identity:
            identity = f"pk:{row.get(pk_name)}"
        digest = _row_digest(identity, {f: row.get(f) for f in fields})
        for i in range(_DIGEST_BYTES):
            fold[i] ^= digest[i]
        n += 1
    return {"n": n, "h": bytes(fold).hex()}


def parity_digests(school, *, entities=None) -> dict:
    """``{entity_type: {"n": int, "h": hex}}`` for every rail entity, or the named ones.

    Returns ``{}`` on any failure, and simply OMITS an entity whose own scan failed - an
    entity that could not be digested is reported by its absence, never as a fabricated
    digest that would read as agreement.
    """
    if not enabled():
        return {}
    try:
        from apps.api.sync_services import _get_entity_config

        config = _get_entity_config(include_derived=True)
    except Exception:  # noqa: BLE001 - no registry, no parity; the cycle is unaffected
        logger.debug("parity: entity registry unavailable", exc_info=True)
        return {}

    want = {str(e).strip().lower() for e in (entities or []) if str(e).strip()}
    out: dict = {}
    for entity_type, (model, allowed) in config.items():
        if want and entity_type not in want:
            continue
        try:
            out[entity_type] = entity_digest(school, entity_type, model, allowed)
        except Exception:  # noqa: BLE001 - one bad entity must not cost the other forty
            logger.debug("parity: digest failed for %s", entity_type, exc_info=True)
    return out


# --------------------------------------------------------------------------- #
# Wire format
# --------------------------------------------------------------------------- #
def encode_digests(digests: dict) -> str:
    """``"student:412:9f3a...,classroom:18:00bb..."`` - compact enough for one header."""
    if not digests:
        return ""
    parts = []
    for entity_type in sorted(digests):
        d = digests.get(entity_type) or {}
        try:
            count = int(d.get("n") or 0)
        except (TypeError, ValueError):
            continue
        parts.append(f"{entity_type}:{count}:{str(d.get('h') or '')[:_HEADER_HEX]}")
    return ",".join(parts)


def decode_digests(raw: str) -> dict:
    """Inverse of :func:`encode_digests`. A malformed segment is dropped, not raised on:
    the sender may be a version this one has never met."""
    out: dict = {}
    for segment in (raw or "").split(","):
        segment = segment.strip()
        if not segment:
            continue
        bits = segment.split(":")
        if len(bits) != 3:
            continue
        entity_type, count, digest = bits[0].strip().lower(), bits[1].strip(), bits[2].strip()
        if not entity_type:
            continue
        try:
            out[entity_type] = {"n": int(count), "h": digest[:_HEADER_HEX]}
        except (TypeError, ValueError):
            continue
    return out


def compare_digests(local: dict, remote: dict) -> dict:
    """Which entities disagree, and how.

    ``drifted`` is the actionable list. ``only_local`` / ``only_remote`` are reported
    separately and are NOT treated as drift: an entity one side does not know about is a
    version or registry difference, and re-pulling it would not fix anything.
    """
    local = local or {}
    remote = remote or {}
    shared = sorted(set(local) & set(remote))
    drifted: list = []
    matched: list = []
    detail: dict = {}
    for entity_type in shared:
        lo = local.get(entity_type) or {}
        re_ = remote.get(entity_type) or {}
        lh = str(lo.get("h") or "")[:_HEADER_HEX]
        rh = str(re_.get("h") or "")[:_HEADER_HEX]
        ln = int(lo.get("n") or 0)
        rn = int(re_.get("n") or 0)
        if lh == rh and ln == rn:
            matched.append(entity_type)
            continue
        drifted.append(entity_type)
        detail[entity_type] = {
            "local_rows": ln,
            "remote_rows": rn,
            "row_delta": rn - ln,
            # The distinction an operator needs first: a row-count difference is missing
            # or extra ROWS, while equal counts with different digests is the same rows
            # holding different VALUES - a stale apply, not a lost record.
            "kind": "row_count" if ln != rn else "row_values",
        }
    return {
        "matched": matched,
        "drifted": drifted,
        "detail": detail,
        "only_local": sorted(set(local) - set(remote)),
        "only_remote": sorted(set(remote) - set(local)),
        "in_parity": not drifted and bool(shared),
    }


#: Entities named in the one-line summary before it elides the rest.
_DESCRIBE_LIMIT = 5  # magic-number-allow: entities named in the parity summary


def describe(comparison: dict) -> str:
    """One sentence for the Sync Center. Empty when everything agreed."""
    drifted = (comparison or {}).get("drifted") or []
    if not drifted:
        return ""
    detail = (comparison or {}).get("detail") or {}
    bits = []
    for entity_type in drifted[:_DESCRIBE_LIMIT]:
        d = detail.get(entity_type) or {}
        delta = d.get("row_delta")
        if d.get("kind") == "row_count" and delta:
            bits.append(f"{entity_type} ({delta:+d} rows)")
        else:
            bits.append(f"{entity_type} (values)")
    more = f" and {len(drifted) - _DESCRIBE_LIMIT} more" if len(drifted) > _DESCRIBE_LIMIT else ""
    return "parity drift: " + ", ".join(bits) + more


def rank_for_flush(comparison: dict) -> list:
    """Drifted entities worst-first, so a capped flush repairs the biggest hole first.

    Missing rows outrank differing values: an absent record is data the box cannot show
    at all, while a stale value is at least present and will also be corrected by the
    same flush when its turn comes.
    """
    detail = (comparison or {}).get("detail") or {}
    drifted = (comparison or {}).get("drifted") or []
    return sorted(
        drifted,
        key=lambda e: (
            0 if (detail.get(e) or {}).get("kind") == "row_count" else 1,
            -abs(int((detail.get(e) or {}).get("row_delta") or 0)),
            e,
        ),
    )


# --------------------------------------------------------------------------- #
# Cadence
# --------------------------------------------------------------------------- #
def due(school, *, force: bool = False) -> bool:
    """Should THIS cycle spend a parity sweep? See :func:`interval_seconds`.

    Claim-on-read: the marker is written the moment the answer is yes, so two cycles
    racing on the same box cannot both decide to sweep. Failing CLOSED (returning False
    on a cache error) is the safe direction - a missed sweep costs an hour of latency on
    a rare fault, an unthrottled one costs the box its cycle.
    """
    if not enabled():
        return False
    if force:
        return True
    try:
        import time

        key = _CACHE_KEY % getattr(school, "pk", school)
        cache = _cache()
        last = cache.get(key)
        now = time.time()
        if last is not None and (now - float(last)) < interval_seconds():
            return False
        cache.set(key, now, interval_seconds() * 2)
        return True
    except Exception:  # noqa: BLE001
        logger.debug("parity: cadence check failed", exc_info=True)
        return False


def reset(school) -> None:
    """Forget the last sweep, so the next cycle takes one. For tests and for an operator
    who has just repaired something and wants the answer NOW rather than within the hour."""
    try:
        _cache().delete(_CACHE_KEY % getattr(school, "pk", school))
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "enabled",
    "interval_seconds",
    "max_flush_entities",
    "entity_digest",
    "parity_digests",
    "encode_digests",
    "decode_digests",
    "compare_digests",
    "describe",
    "rank_for_flush",
    "due",
    "reset",
]
