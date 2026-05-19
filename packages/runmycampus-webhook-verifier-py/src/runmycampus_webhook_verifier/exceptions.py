"""Typed exception hierarchy for the verifier.

All errors raised by the strict verifier paths derive from
:class:`VerificationError` so callers can ``except VerificationError``
once and capture every failure mode.

The lenient ``verify_signature(...)`` boolean entry point swallows
exceptions internally and returns ``False`` instead; reach for the
strict variants when you want to log *why* a verification failed
without leaking secret material in the log line.
"""

from __future__ import annotations


class VerificationError(Exception):
    """Base class for every verifier failure mode.

    Carry no payload / secret material — only metadata strings safe
    to log.
    """


class MissingHeaderError(VerificationError):
    """Required HMAC header was absent or empty.

    Raised when the inbound request does not contain a usable
    ``X-RunMyCampus-Signature`` header (None / empty string / whitespace-only).
    """


class UnsupportedAlgorithmError(VerificationError):
    """The signature prefix advertises an algorithm we cannot verify.

    Currently the SDK only verifies ``sha256=<hex>``. Receiving e.g.
    ``sha512=...`` from a future platform rollout that the customer
    has not yet upgraded the SDK for will raise this — fail closed
    rather than silently accept.
    """


class BadSignatureError(VerificationError):
    """The signature did not match the HMAC of the body under our secret.

    The body may have been tampered with, OR the secret is wrong, OR
    the body bytes are not the canonical bytes the platform signed.
    Constant-time compare ensures we never leak which one through timing.
    """


class ClockSkewError(VerificationError):
    """The signed timestamp is outside the accepted tolerance window.

    Defends against replay attacks: an attacker who steals a valid
    (body + signature) pair can otherwise resubmit it indefinitely.
    Default tolerance is 300 seconds (5 minutes), matching Stripe /
    GitHub conventions.

    Attribute ``skew_seconds`` carries the absolute skew so a debug
    log line can show the magnitude without revealing the timestamp
    itself (which is part of the signed payload contract).
    """

    def __init__(self, message: str, skew_seconds: float = 0.0) -> None:
        super().__init__(message)
        self.skew_seconds = skew_seconds


__all__ = [
    "VerificationError",
    "MissingHeaderError",
    "UnsupportedAlgorithmError",
    "BadSignatureError",
    "ClockSkewError",
]
