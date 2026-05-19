"""Canonical JSON serializer used for webhook signing.

The serializer is **deliberately minimal and pinned to RFC 8785-style
conventions** so it matches the JavaScript twin byte-for-byte:

* Object keys sorted lexicographically by their UTF-16 code-unit order
  (the natural Python ``sorted()`` order on str AND the natural JS
  ``Array.prototype.sort()`` order on object keys — both compare by
  code-unit, NOT Unicode codepoint).
* No whitespace between tokens (separators ``(",", ":")``).
* UTF-8 output bytes.
* Non-ASCII characters emitted literally (NOT ``\\uXXXX``-escaped) so
  the output matches what ``JSON.stringify`` produces by default.
* No support for ``NaN`` / ``Infinity`` / ``-Infinity`` — those are
  not valid JSON and we refuse to emit them; raise ``ValueError``.
* Floats are emitted via ``repr`` round-tripping; integers as the
  base-10 form. (Avoid sending floats over webhooks if you can help it
  — different runtimes disagree on trailing zeros. Send strings.)

Byte-for-byte parity with the JS twin (``canonical.ts``) is verified
by ``tests/test_canonical.py`` against the shared fixture file at
``../runmycampus-webhook-verifier-js/test/fixtures/canonical-cases.json``.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


class CanonicalJSONError(ValueError):
    """Raised when an input cannot be canonically serialized.

    Most commonly: ``float('nan')`` / ``float('inf')`` / unsupported
    object types. We refuse to silently lossy-coerce — that would
    let the platform and receiver disagree on the signed bytes and
    produce verification failures that look like tampering.
    """


def _reject_nonfinite(value: float) -> None:
    """Refuse NaN / +Inf / -Inf — JSON does not represent them."""
    if math.isnan(value) or math.isinf(value):
        raise CanonicalJSONError(
            "canonical JSON: NaN / Infinity / -Infinity are not "
            "representable; coerce to None / string upstream."
        )


def canonicalize(value: Any) -> bytes:
    """Return canonical UTF-8 bytes for ``value``.

    ``value`` may be any JSON-compatible Python structure:
    ``dict``, ``list``, ``str``, ``int``, ``float``, ``bool``, or
    ``None``. Anything else raises :class:`CanonicalJSONError` via
    :func:`json.dumps`' ``default=`` hook.

    Determinism contract:
        For any two semantically-equal inputs, the output bytes are
        identical. ``canonicalize({"b":2,"a":1})`` and
        ``canonicalize({"a":1,"b":2})`` both produce ``b'{"a":1,"b":2}'``.
    """

    def _default(obj: Any) -> Any:
        # We intentionally do NOT serialize bytes / datetimes / Decimal —
        # those are application concerns. Coerce them upstream.
        raise CanonicalJSONError(
            f"canonical JSON: type {type(obj).__name__!r} is not "
            "JSON-serializable; coerce upstream."
        )

    # First pass: walk the tree to reject non-finite floats so the
    # error surfaces here (json.dumps would silently emit ``NaN`` /
    # ``Infinity`` literals which violate strict JSON).
    _walk_reject_nonfinite(value)

    text = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=_default,
    )
    return text.encode("utf-8")


def _walk_reject_nonfinite(value: Any) -> None:
    """Depth-first walk that calls :func:`_reject_nonfinite` on floats."""
    if isinstance(value, float):
        _reject_nonfinite(value)
        return
    if isinstance(value, dict):
        for v in value.values():
            _walk_reject_nonfinite(v)
        return
    if isinstance(value, (list, tuple)):
        for v in value:
            _walk_reject_nonfinite(v)
        return
    # str / int / bool / None / other: nothing to check.


def canonical_sha256_hex(value: Any) -> str:
    """Return ``sha256(canonicalize(value))`` as a lowercase hex string.

    Convenience for parity-verification fixtures. Customers should
    NOT use this as a substitute for HMAC — sha256 of the body without
    a secret is not authentication, only a hash.
    """
    return hashlib.sha256(canonicalize(value)).hexdigest()


__all__ = ["canonicalize", "canonical_sha256_hex", "CanonicalJSONError"]
