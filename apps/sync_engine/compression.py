"""Gzip on the sync wire (G6) — explicit, per-endpoint, in BOTH directions.

Delta bundles are NDJSON: one repeated JSON object shape per line, the same field names
on every row. That is about as compressible as a payload gets, and until now nothing on
the sync rail was compressed at all — not the cloud->box bundle download (31,043 rows on
one measured box), not the box->cloud bundle upload. On a village link paid for by the
megabyte that is the single largest avoidable cost in the protocol.

WHY NOT ``GZipMiddleware``
-------------------------
Django ships ``django.middleware.gzip.GZipMiddleware`` and adding it to ``MIDDLEWARE``
would have been a one-line change. It is the wrong mechanism here, for three reasons:

1. **Blast radius.** The middleware compresses EVERY response the project serves — every
   tenant HTML page, every admin view, every DRF endpoint. This app has a documented
   history of site-wide middleware changes surfacing as unrelated 500s and 502s. The
   thing that needs compressing is two machine-to-machine endpoints; compressing 400 more
   to get them is not a trade worth making, and it is a change to a file four other
   agents are editing.
2. **BREACH.** Compressing a response that mixes attacker-influenced input with a secret
   (a CSRF token in an HTML form, a session-bound value) leaks the secret through
   compressed length. Django's own middleware mitigates this only partially (it skips
   responses under 200 bytes and randomises nothing). The sync bundle endpoints are safe
   to compress for a specific, checkable reason: their bodies are HMAC-signed NDJSON
   built from tenant rows, they carry no CSRF token, no session cookie and no
   ``Set-Cookie``, and they are authenticated by a bearer credential rather than by an
   ambient cookie — so there is no cross-site request an attacker can cause a browser to
   make against them. That reasoning holds for THESE endpoints and is exactly what does
   not hold for the site's HTML.
3. **Streaming.** ``GZipMiddleware`` handles ``StreamingHttpResponse`` by wrapping the
   iterator and dropping ``Content-Length``. The download endpoint returns a buffered
   ``HttpResponse`` today, but the G2 paging work exists precisely so it can stop
   building the whole corpus in memory; a compression layer that behaves differently the
   day that response becomes streaming is a trap laid for a future change.

So compression is applied explicitly, at the two views that produce bundles, on request.

REQUEST bodies are the other half. ``Accept-Encoding`` only gets the DOWNLOAD compressed;
the box's own PUSH is a request body, and HTTP has no negotiation for that — a client
either declares ``Content-Encoding: gzip`` and hopes, or it does not. A cloud that
predates this decodes nothing and hands gzip bytes to ``verify_and_parse_bundle``, which
does ``data.decode("utf-8")`` and raises. So the box does NOT guess: the cloud ADVERTISES
that it decodes request bodies (``X-RMC-Sync-Accept-Encoding``) on responses the box was
already collecting, the box remembers that per peer, and only then compresses what it
pushes. A box that has never seen the advert pushes exactly as it does today.

Nothing here may ever fail a transfer. Every entry point degrades to "uncompressed",
which is always correct and merely bigger.
"""
from __future__ import annotations

import gzip
import logging
import zlib
from urllib.parse import urlsplit

from django.conf import settings

logger = logging.getLogger(__name__)

GZIP = "gzip"

#: The cloud stamps this on the bundle responses to say it can DECODE a gzip request
#: body. ``Accept-Encoding`` is a request header and cannot carry this the other way, and
#: there is no standard response header that means "I decode gzip uploads" — so it is a
#: named RMC header alongside the other handshakes on the same responses.
SYNC_ACCEPT_ENCODING_HEADER = "X-RMC-Sync-Accept-Encoding"

#: Below this, the gzip container (~20 bytes of header/trailer) plus the CPU is not worth
#: it and can make the body LARGER. Django's own middleware uses the same idea at 200.
MIN_COMPRESS_BYTES = 256  # magic-number-allow: gzip floor, below which framing costs more than it saves

#: Ceiling on what a gzip REQUEST body may expand to. A 64 MiB cap on a rail whose
#: receiver already refuses more than ``RMC_SYNC_BUNDLE_MAX_ROWS`` rows is generous, and
#: without it a few kilobytes of crafted gzip is an out-of-memory on the operator.
DEFAULT_MAX_DECOMPRESSED_BYTES = 64 * 1024 * 1024  # magic-number-allow: decompression bomb ceiling

#: How long the box remembers that a peer decodes gzip request bodies. Long enough that
#: it is learned once and used for a day; short enough that a cloud rolled BACK is
#: forgotten without an operator having to know this cache exists.
_PEER_MEMORY_SECONDS = 24 * 3600  # magic-number-allow: peer capability memory (24h, seconds)
_PEER_KEY = "rmc:sync:peer_accepts_gzip:%s"


#: Every failure mode the soft paths below can actually produce: a cache backend that
#: is unreachable or misconfigured, a response object that is not the shape expected, a
#: malformed encoding token, a bad gzip stream. NAMED rather than a blanket
#: ``except Exception`` on purpose. Compression must never fail a transfer -- but that
#: promise is the kind a blanket hides a bug behind, and a rail that ships uncompressed
#: because of a TypeError in here is indistinguishable from one an operator turned off.
_SOFT_FAILURES = (
    AttributeError,
    ImportError,
    LookupError,
    OSError,  # gzip.BadGzipFile is an OSError
    RuntimeError,
    TypeError,
    ValueError,
    zlib.error,
)


def enabled() -> bool:
    """Master switch. Off restores the exact pre-G6 wire byte-for-byte."""
    return bool(getattr(settings, "RMC_SYNC_WIRE_COMPRESSION_ENABLED", True))


def max_decompressed_bytes() -> int:
    try:
        return max(
            1,
            int(
                getattr(
                    settings,
                    "RMC_SYNC_MAX_DECOMPRESSED_BUNDLE_BYTES",
                    DEFAULT_MAX_DECOMPRESSED_BYTES,
                )
            ),
        )
    except (TypeError, ValueError):
        return DEFAULT_MAX_DECOMPRESSED_BYTES


def compress(data: bytes) -> bytes:
    """gzip ``data`` deterministically.

    ``mtime=0`` so the same bundle compresses to the same bytes on every call — a bundle
    is HMAC-signed over its PLAINTEXT, but a deterministic container makes a transfer
    reproducible and a test able to assert on bytes rather than on "roughly smaller".
    """
    return gzip.compress(data, compresslevel=6, mtime=0)


def decompress(data: bytes, *, max_bytes: int | None = None) -> bytes:
    """Inflate a gzip stream, refusing to expand past ``max_bytes``.

    Raises ``ValueError`` on a corrupt stream or on overflow. Bounded on purpose: this
    runs on the OPERATOR, for a body an authenticated box supplied, and an unbounded
    ``gzip.decompress`` turns a small upload into an out-of-memory. The bound is checked
    DURING inflation (``decompressobj`` with ``max_length``), not after, because checking
    afterwards means the allocation already happened.
    """
    cap = max_bytes if max_bytes is not None else max_decompressed_bytes()
    try:
        # 16 + MAX_WBITS selects the gzip container (as opposed to a raw zlib stream).
        obj = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = obj.decompress(data, cap)
        if obj.unconsumed_tail:
            raise ValueError("decompressed_bundle_too_large")
        out += obj.flush()
        if len(out) > cap:
            raise ValueError("decompressed_bundle_too_large")
        return out
    except ValueError:
        raise
    except zlib.error as exc:
        raise ValueError(f"invalid_gzip_body:{exc}") from exc


def wants_gzip(accept_encoding: str) -> bool:
    """Does this ``Accept-Encoding`` value ask for gzip?

    Deliberately simple: a token match with an explicit ``;q=0`` refusal honoured. Full
    RFC 9110 quality negotiation would be more code than the one client that sends this
    header can ever exercise, and getting it wrong in the permissive direction sends a
    body a peer cannot read.
    """
    if not accept_encoding:
        return False
    for part in str(accept_encoding).split(","):
        bits = part.strip().split(";")
        token = bits[0].strip().lower()
        if token not in (GZIP, "*"):
            continue
        for param in bits[1:]:
            key, _, value = param.partition("=")
            if key.strip().lower() == "q":
                try:
                    if float(value.strip()) == 0:
                        return False
                except ValueError:
                    return False
        return True
    return False


def compress_response(request, response):
    """Gzip ``response`` in place when the caller asked for it. Returns the response.

    No-ops (and says so via the absent header) for a streaming response, an already
    encoded one, a body under :data:`MIN_COMPRESS_BYTES`, a client that did not ask, or
    any failure at all. ``Vary: Accept-Encoding`` is set whenever the endpoint is willing
    to vary — including when it decides not to compress THIS body — because a cache that
    stores an uncompressed answer under a key that ignores the header will later serve it
    to a client that asked for gzip, and vice versa.
    """
    try:
        from django.utils.cache import patch_vary_headers

        patch_vary_headers(response, ("Accept-Encoding",))
        if not enabled():
            return response
        if response.get("Content-Encoding"):
            return response
        if getattr(response, "streaming", False):
            return response
        accept = request.META.get("HTTP_ACCEPT_ENCODING", "") if request is not None else ""
        if not wants_gzip(accept):
            return response
        body = response.content
        if len(body) < MIN_COMPRESS_BYTES:
            return response
        packed = compress(body)
        if len(packed) >= len(body):
            # Already-compressed or pathological content. Shipping the larger body would
            # be a straight loss, and the client is required to accept either.
            return response
        response.content = packed
        response["Content-Encoding"] = GZIP
        response["Content-Length"] = str(len(packed))
    except _SOFT_FAILURES:
        logger.debug("bundle response compression skipped", exc_info=True)
    return response


def request_body(request, *, max_bytes: int | None = None) -> bytes:
    """The request body, inflated when the sender declared ``Content-Encoding: gzip``.

    Raises ``ValueError`` when the declared encoding is unsupported or the stream is bad,
    so the view can answer 400 rather than letting ``verify_and_parse_bundle`` die on
    ``data.decode("utf-8")`` with a 500 — which is exactly what an un-upgraded operator
    does with a gzip body, and the reason the box waits for the advert before sending one.
    """
    raw = request.body or b""
    encoding = (request.META.get("HTTP_CONTENT_ENCODING") or "").strip().lower()
    if not encoding or encoding == "identity":
        return raw
    if encoding != GZIP:
        raise ValueError(f"unsupported_content_encoding:{encoding}")
    return decompress(raw, max_bytes=max_bytes)


# --------------------------------------------------------------------------- #
# Peer capability memory (box side)
# --------------------------------------------------------------------------- #
def peer_key(endpoint: str) -> str:
    """``scheme://host`` for ``endpoint``.

    Keyed by ORIGIN, not by path: the box learns the advert on the DOWNLOAD response and
    needs it on the UPLOAD request, and those are two different paths on one cloud.
    """
    try:
        parts = urlsplit(str(endpoint or ""))
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
    except ValueError:
        pass
    return str(endpoint or "")


def remember_peer_accepts_gzip(endpoint: str, accepted: bool) -> None:
    """Record what a peer said about decoding gzip REQUEST bodies. Never raises."""
    try:
        from django.core.cache import cache

        cache.set(_PEER_KEY % peer_key(endpoint), bool(accepted), _PEER_MEMORY_SECONDS)
    except _SOFT_FAILURES:
        logger.debug("could not remember peer gzip capability", exc_info=True)


def peer_accepts_gzip(endpoint: str) -> bool:
    """Has this peer advertised that it decodes a gzip request body?

    ``False`` when unknown, which is the pre-G6 behaviour and always safe.
    """
    if not enabled():
        return False
    try:
        from django.core.cache import cache

        return bool(cache.get(_PEER_KEY % peer_key(endpoint), False))
    except _SOFT_FAILURES:
        return False


def forget_peer(endpoint: str) -> None:
    """Drop a peer's advert — called when a compressed push was rejected."""
    try:
        from django.core.cache import cache

        cache.delete(_PEER_KEY % peer_key(endpoint))
    except _SOFT_FAILURES:
        logger.debug("could not forget peer gzip capability", exc_info=True)


def read_peer_advert(headers, endpoint: str) -> None:
    """Learn (or unlearn) a peer's upload-gzip support from a response's headers.

    Absent header means "unknown", NOT "no": an older cloud sends nothing, and unlearning
    on absence would make a mixed fleet flap. Only an explicit value teaches anything.
    """
    try:
        if headers is None:
            return
        raw = headers.get(SYNC_ACCEPT_ENCODING_HEADER)
        if raw is None:
            return
        remember_peer_accepts_gzip(endpoint, wants_gzip(raw))
    except _SOFT_FAILURES:
        logger.debug("could not read peer gzip advert", exc_info=True)


def decode_response_body(headers, body: bytes) -> bytes:
    """Inflate a response body the peer said was gzipped.

    ``urllib`` does NOT do this. Sending ``Accept-Encoding: gzip`` without decoding the
    answer hands gzip bytes to ``verify_and_parse_bundle`` — i.e. it silently corrupts
    every bundle it receives — so this function is not an optimisation, it is the other
    half of asking.
    """
    try:
        if not body or headers is None:
            return body
        encoding = (headers.get("Content-Encoding") or "").strip().lower()
        if encoding != GZIP:
            return body
        return decompress(body)
    except ValueError:
        logger.warning("could not inflate a gzip response body; passing it through")
        return body
    except _SOFT_FAILURES:
        logger.debug("response decode skipped", exc_info=True)
        return body


__all__ = [
    "GZIP",
    "SYNC_ACCEPT_ENCODING_HEADER",
    "MIN_COMPRESS_BYTES",
    "compress",
    "compress_response",
    "decode_response_body",
    "decompress",
    "enabled",
    "forget_peer",
    "max_decompressed_bytes",
    "peer_accepts_gzip",
    "peer_key",
    "read_peer_advert",
    "remember_peer_accepts_gzip",
    "request_body",
    "wants_gzip",
]
