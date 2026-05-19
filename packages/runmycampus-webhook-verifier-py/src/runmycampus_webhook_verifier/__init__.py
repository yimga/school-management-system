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
    LEGACY_SIGNATURE_HEADER,
    LEGACY_TIMESTAMP_HEADER,
    LEGACY_EVENT_HEADER,
    LEGACY_VERSION_HEADER,
    SUPPORTED_PREFIX,
    DEFAULT_TOLERANCE_SECONDS,
    compute_signature,
    verify_signature,
    verify_signature_strict,
    verify,
    VerifyResult,
)
from ._canonical import canonicalize, canonical_sha256_hex
from .exceptions import (
    VerificationError,
    ClockSkewError,
    MissingHeaderError,
    BadSignatureError,
    UnsupportedAlgorithmError,
)

__version__ = "1.0.0-rc.1"

__all__ = [
    "__version__",
    "SIGNATURE_HEADER",
    "TIMESTAMP_HEADER",
    "EVENT_HEADER",
    "VERSION_HEADER",
    "LEGACY_SIGNATURE_HEADER",
    "LEGACY_TIMESTAMP_HEADER",
    "LEGACY_EVENT_HEADER",
    "LEGACY_VERSION_HEADER",
    "SUPPORTED_PREFIX",
    "DEFAULT_TOLERANCE_SECONDS",
    "compute_signature",
    "verify_signature",
    "verify_signature_strict",
    "verify",
    "VerifyResult",
    "canonicalize",
    "canonical_sha256_hex",
    "VerificationError",
    "ClockSkewError",
    "MissingHeaderError",
    "BadSignatureError",
    "UnsupportedAlgorithmError",
]
