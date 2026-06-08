"""Account-free, self-hosted login bot defense (2026-06-08).

Three layers, none of which require a third-party account, external service, or
network call — everything is signed in-process, so it works offline and keeps
the platform's local-first / no-cloud-dependency posture:

1. **Honeypot** — a hidden form field real users never fill. A non-empty value
   is an automated submitter. Zero friction, zero false positives.
2. **Timing trap** — a signed render-timestamp embedded in the form. A login
   submitted implausibly fast (sub-second) is a script, not a person. Only
   rejects when the token is present AND verifiably too fast, so a stale/missing
   token never blocks a real user.
3. **Proof-of-work** — after a failed attempt we issue a signed challenge; the
   browser must find a nonce whose ``sha256(salt:nonce)`` has N leading zero
   bits (~1s of CPU), then submit it. We verify in microseconds. The challenge
   is HMAC-signed + TTL'd + single-use, so it is fully stateless (no DB row).

All three are belt-and-suspenders on the always-on ``login_guard`` lockout.
The PoW replaces Cloudflare Turnstile as the default challenge (no account, no
``challenges.cloudflare.com`` script). Turnstile remains available as an opt-in
alternative when its keys are set.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time

from django.conf import settings
from django.core import signing
from django.core.cache import cache

logger = logging.getLogger(__name__)

_POW_SIGNING_SALT = "rmc-login-pow"
_TIMING_SIGNING_SALT = "rmc-login-timing"
_POW_SEEN_PREFIX = "login-pow-seen:v1"

# Defaults (overridable in config/settings.py via env).
_DEFAULT_POW_BITS = 18  # ~260k sha256 hashes ≈ <1s on a normal device
_DEFAULT_POW_TTL = 600  # magic-number-allow: PoW challenge valid 10 min
_DEFAULT_FORM_TTL = 7200  # magic-number-allow: login form token valid 2h
_DEFAULT_MIN_FORM_SECONDS = 1.0  # humans don't submit a login in under a second


# ── Proof-of-work ──────────────────────────────────────────────────────────
def pow_enabled() -> bool:
    return bool(getattr(settings, "LOGIN_POW_ENABLED", True))


def _pow_bits() -> int:
    return int(getattr(settings, "LOGIN_POW_BITS", _DEFAULT_POW_BITS))


def _pow_ttl() -> int:
    return int(getattr(settings, "LOGIN_POW_TTL_SECONDS", _DEFAULT_POW_TTL))


def issue_pow_challenge(session_key: str = "") -> dict:
    """Fresh signed challenge. Returns ``{token, salt, bits}`` for the template.

    ``salt``/``bits`` are exposed so the browser solver can run; the server
    re-reads them from the signed ``token`` on verify, so a tampered salt/bits
    cannot weaken the check. When ``session_key`` is supplied it is bound into
    the token, so a solved challenge cannot be replayed from a different session.

    Replay is also guarded single-use via the cache in :func:`verify_pow`; that
    guard is globally correct only with a shared cache (``REDIS_URL``). Under the
    per-process LocMemCache the session binding here is the primary anti-replay
    control, and re-solving costs ~1s of CPU per attempt regardless.
    """
    salt = secrets.token_hex(16)
    bits = _pow_bits()
    jti = secrets.token_urlsafe(9)
    payload = {"s": salt, "b": bits, "j": jti}
    if session_key:
        payload["sk"] = session_key
    token = signing.dumps(payload, salt=_POW_SIGNING_SALT)
    return {"token": token, "salt": salt, "bits": bits}


def _leading_zero_bits(digest: bytes) -> int:
    n = 0
    for byte in digest:
        if byte == 0:
            n += 8
            continue
        n += 8 - byte.bit_length()
        break
    return n


def verify_pow(token: str, nonce: str, session_key: str = "") -> bool:
    """True when ``nonce`` solves the signed, unexpired, single-use ``token``.

    When the challenge was issued bound to a session (``sk`` in the token), the
    caller's ``session_key`` must match — a token solved in one session cannot be
    replayed from another.
    """
    if not token or nonce is None or str(nonce) == "":
        return False
    try:
        data = signing.loads(token, salt=_POW_SIGNING_SALT, max_age=_pow_ttl())
    except (signing.BadSignature, signing.SignatureExpired, ValueError, TypeError):
        return False
    bound = str(data.get("sk", ""))
    if bound and bound != (session_key or ""):
        return False
    salt = str(data.get("s", ""))
    bits = int(data.get("b", 0))
    if not salt or bits <= 0:
        return False
    digest = hashlib.sha256(f"{salt}:{nonce}".encode("utf-8")).digest()
    if _leading_zero_bits(digest) < bits:
        return False
    # Single-use (best-effort): a solved token cannot be replayed within its TTL.
    seen_key = f"{_POW_SEEN_PREFIX}:{hashlib.sha256(token.encode()).hexdigest()[:24]}"
    try:
        if not cache.add(seen_key, 1, _pow_ttl()):
            return False
    except Exception:  # noqa: BLE001 - cache down → skip replay guard, never block
        logger.warning("login_pow_replay_cache_unavailable", exc_info=True)
    return True


# ── Honeypot ───────────────────────────────────────────────────────────────
def honeypot_field_name() -> str:
    return str(getattr(settings, "LOGIN_HONEYPOT_FIELD", "company_url"))


def honeypot_tripped(request) -> bool:
    """True when the hidden field was filled (only automated submitters do)."""
    return bool((request.POST.get(honeypot_field_name()) or "").strip())


# ── Timing trap ────────────────────────────────────────────────────────────
def _form_ttl() -> int:
    return int(getattr(settings, "LOGIN_FORM_TOKEN_TTL_SECONDS", _DEFAULT_FORM_TTL))


def _min_form_seconds() -> float:
    return float(getattr(settings, "LOGIN_MIN_FORM_SECONDS", _DEFAULT_MIN_FORM_SECONDS))


def issue_form_timestamp() -> str:
    """Signed render time, embedded in the form for the timing trap."""
    return signing.dumps({"t": time.time()}, salt=_TIMING_SIGNING_SALT)


def timing_tripped(request) -> bool:
    """True ONLY when a valid token proves the form was submitted too fast.

    A missing / expired / tampered token returns False (benign — could be a
    cached page or a long-idle tab), so the trap never blocks a real user; it
    only fires on a verifiably sub-second submission.
    """
    min_seconds = _min_form_seconds()
    if min_seconds <= 0:
        return False
    token = request.POST.get("form_ts") or ""
    if not token:
        return False
    try:
        data = signing.loads(token, salt=_TIMING_SIGNING_SALT, max_age=_form_ttl())
    except (signing.BadSignature, signing.SignatureExpired, ValueError, TypeError):
        return False
    issued = float(data.get("t", 0) or 0)
    if issued <= 0:
        return False
    return (time.time() - issued) < min_seconds


__all__ = [
    "pow_enabled",
    "issue_pow_challenge",
    "verify_pow",
    "honeypot_field_name",
    "honeypot_tripped",
    "issue_form_timestamp",
    "timing_tripped",
]
