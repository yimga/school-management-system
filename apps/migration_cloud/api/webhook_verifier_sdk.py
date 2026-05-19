# DEPRECATED: vendored copy; prefer `pip install runmycampus-webhook-verifier`.
# Will remain available through v4.0.0.
#
# This single-file copy is preserved for air-gapped installs and for
# customers who haven't yet adopted the packaged SDK. The packaged
# version at packages/runmycampus-webhook-verifier-py/ ships the same
# core verify_signature() PLUS typed-exception strict mode + clock-skew
# enforcement + exported canonical-JSON serializer. Output bytes are
# byte-for-byte identical (asserted in CI by
# tests/test_verifier.py::StandaloneVendoredParityTests).
"""RunMyCampus Migration Cloud — webhook signature verifier (Python, DEPRECATED VENDORED COPY).

Copy-paste deployable. Zero imports outside the Python standard library.
No RunMyCampus dependencies. Drop this file into your webhook receiver's
codebase, import :func:`verify_signature`, and call it on every inbound
delivery before trusting the body.

The platform signs every outbound webhook payload with HMAC-SHA256 over
the **canonical** JSON form of the payload (sorted keys, no whitespace,
UTF-8). The signature ships in the ``X-RunMyCampus-Signature`` header in
the form::

    sha256=<lowercase-hex-digest>

Constant-time comparison (``hmac.compare_digest``) is used to defeat
timing attacks; do not replace it with ``==``.

Quickstart
----------

::

    from webhook_verifier_sdk import verify_signature

    @app.route("/hooks/runmycampus", methods=["POST"])
    def receive_webhook():
        raw = request.get_data()
        header = request.headers.get("X-RunMyCampus-Signature", "")
        if not verify_signature(raw, header, MY_SECRET):
            abort(401)
        # body is trustworthy — handle as normal
        ...

Compatibility
-------------

* Python 3.8+
* Stdlib only — works in air-gapped / locked-down environments.

License: MIT.
"""

from __future__ import annotations

import hmac
import hashlib
from typing import Union


# Public header name the platform writes; do not hard-code in caller code.
SIGNATURE_HEADER = "X-RunMyCampus-Signature"

# Signature prefix that identifies the digest algorithm. Currently only
# ``sha256`` is emitted; the prefix is checked so a future ``sha512=``
# rollout fails closed in old verifiers (rather than silently passing
# whatever a malicious sender supplies).
SUPPORTED_PREFIX = "sha256="


def _coerce_bytes(value: Union[str, bytes, bytearray, memoryview]) -> bytes:
    """Normalize ``str | bytes | bytearray | memoryview`` to ``bytes``."""
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    return value


def compute_signature(
    body: Union[str, bytes, bytearray, memoryview],
    secret: Union[str, bytes, bytearray, memoryview],
) -> str:
    """Return ``sha256=<hex>`` for the given raw body + secret.

    Useful for unit tests, replay tooling, and debugging signature
    mismatches. Do NOT use the output to compare against a header with
    ``==``; use :func:`verify_signature` so the compare runs in constant
    time.
    """
    body_bytes = _coerce_bytes(body)
    secret_bytes = _coerce_bytes(secret)
    digest = hmac.new(secret_bytes, body_bytes, hashlib.sha256).hexdigest()
    return SUPPORTED_PREFIX + digest


def verify_signature(
    body: Union[str, bytes, bytearray, memoryview],
    header_value: Union[str, bytes, None],
    secret: Union[str, bytes, bytearray, memoryview],
) -> bool:
    """Return True iff ``header_value`` is a valid signature for ``body``.

    Args:
        body: The raw request body bytes (or string). MUST be the exact
            bytes the platform signed — do NOT re-serialize the JSON or
            change key ordering before passing here.
        header_value: The value of the ``X-RunMyCampus-Signature`` header
            from the inbound request. Defensive: accepts ``None`` /
            empty / wrong prefix → returns False.
        secret: The shared HMAC secret you received from the platform at
            subscription creation time. Treat as opaque material.

    Returns:
        bool — True only when the prefix is supported AND the digest
        matches the body. Constant-time compare via
        :func:`hmac.compare_digest`.
    """
    if header_value is None:
        return False
    if isinstance(header_value, (bytes, bytearray, memoryview)):
        try:
            header_str = bytes(header_value).decode("utf-8")
        except UnicodeDecodeError:
            return False
    else:
        header_str = header_value
    header_str = header_str.strip()
    if not header_str.startswith(SUPPORTED_PREFIX):
        return False
    expected = compute_signature(body, secret)
    # hmac.compare_digest accepts equal-length str OR equal-length bytes;
    # encode both sides to bytes so a unicode-encoded header still compares.
    return hmac.compare_digest(
        expected.encode("ascii"),
        header_str.encode("ascii"),
    )


__all__ = [
    "SIGNATURE_HEADER",
    "SUPPORTED_PREFIX",
    "compute_signature",
    "verify_signature",
]
