"""runmycampus-webhook-verifier — official Python verifier for RunMyCampus webhooks.

Stdlib-only. Zero third-party runtime dependencies. Works on Python 3.8+
including locked-down / air-gapped environments.

Public API::

    from runmycampus_webhook_verifier import (
        verify_signature,
        compute_signature,
        canonicalize,
        VerificationError,
        ClockSkewError,
        MissingHeaderError,
    )

See README.md for installation and framework-specific examples.
"""

from __future__ import annotations

from .verifier import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    EVENT_HEADER,
    VERSION_HEADER,
    SUPPORTED_PREFIX,
    DEFAULT_TOLERANCE_SECONDS,
    compute_signature,
    verify_signature,
    verify_signature_strict,
)
from ._canonical import canonicalize, canonical_sha256_hex
from .exceptions import (
    VerificationError,
    ClockSkewError,
    MissingHeaderError,
    BadSignatureError,
    UnsupportedAlgorithmError,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "SIGNATURE_HEADER",
    "TIMESTAMP_HEADER",
    "EVENT_HEADER",
    "VERSION_HEADER",
    "SUPPORTED_PREFIX",
    "DEFAULT_TOLERANCE_SECONDS",
    "compute_signature",
    "verify_signature",
    "verify_signature_strict",
    "canonicalize",
    "canonical_sha256_hex",
    "VerificationError",
    "ClockSkewError",
    "MissingHeaderError",
    "BadSignatureError",
    "UnsupportedAlgorithmError",
]
