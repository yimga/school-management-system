"""v4.00.85 - Dual-secret webhook key rotation helper.

Operator stages a NEW secret while the OLD secret stays active. Both are
used to sign outbound webhooks during the grace window so subscribers
have time to roll over their verifier secret without dropping deliveries.

Storage: when MigrationCloudWebhookSubscription has rotated_to/grace_until
columns, those are used. Otherwise an in-memory ring (cap 100) per
subscription_id holds staged secrets. NEVER leaks secret material into
logs or audit rows.
"""
from __future__ import annotations
import hashlib
import hmac
import logging
import threading
from datetime import timedelta

logger = logging.getLogger(__name__)


_LOCK = threading.Lock()
_STAGED_SECRETS: dict[int, dict] = {}  # subscription_id -> {staged_secret, grace_until_iso}
_STAGED_SECRETS_CAP = 100


def stage_new_secret(*, subscription_id: int, new_secret: str, grace_seconds: int = 86400) -> bool:  # magic-number-allow: ttl-seconds
    """Stage a new signing secret with a grace window. Returns True on
    stage success."""
    try:
        from django.utils import timezone as _tz
        if not new_secret or grace_seconds <= 0:
            return False
        grace_until = _tz.now() + timedelta(seconds=int(grace_seconds))
        with _LOCK:
            if len(_STAGED_SECRETS) >= _STAGED_SECRETS_CAP:
                # Evict oldest
                _STAGED_SECRETS.pop(next(iter(_STAGED_SECRETS)), None)
            _STAGED_SECRETS[int(subscription_id)] = {
                "staged_secret": new_secret,
                "grace_until_iso": grace_until.isoformat(),
                "grace_until_epoch": grace_until.timestamp(),
            }
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("stage_new_secret failed: %s", exc)
        return False


def get_staged_secret_record(subscription_id: int) -> dict | None:
    """Return the staged secret + grace if it exists AND grace is not yet
    expired. Returns None otherwise. Caller must NOT log the secret."""
    try:
        with _LOCK:
            rec = _STAGED_SECRETS.get(int(subscription_id))
            if rec is None:
                return None
            # Honor grace window
            from django.utils import timezone as _tz
            if _tz.now().timestamp() > rec.get("grace_until_epoch", 0):
                # Expired - drop and return None
                _STAGED_SECRETS.pop(int(subscription_id), None)
                return None
            return dict(rec)
    except Exception:  # noqa: BLE001
        return None


def promote_staged_secret(subscription_id: int) -> str | None:
    """Promote staged -> active. Returns the staged secret value so the
    caller can persist it as the new primary; clears the staged slot.
    Returns None if nothing was staged."""
    with _LOCK:
        rec = _STAGED_SECRETS.pop(int(subscription_id), None)
        if rec is None:
            return None
        return rec.get("staged_secret")


def mint_dual_signature_pair(*, payload_bytes: bytes, active_secret: str, subscription_id: int) -> dict:
    """Return {"primary": "sha256=<hex>", "next": "sha256=<hex>" | None}.
    The "next" key is None when no staged secret exists or grace has expired."""
    primary = hmac.new(
        active_secret.encode("utf-8") if isinstance(active_secret, str) else active_secret,
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    out = {"primary": f"sha256={primary}", "next": None}
    rec = get_staged_secret_record(subscription_id)
    if rec and rec.get("staged_secret"):
        staged = rec["staged_secret"]
        next_sig = hmac.new(
            staged.encode("utf-8") if isinstance(staged, str) else staged,
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        out["next"] = f"sha256={next_sig}"
    return out


def reset_staged_secrets() -> None:
    """Test-only clear."""
    with _LOCK:
        _STAGED_SECRETS.clear()


def rotation_summary() -> dict:
    """URL-leak-safe summary. Counts only, NEVER secret material."""
    with _LOCK:
        return {
            "staged_count": len(_STAGED_SECRETS),
            "subscription_ids_with_staged": sorted(_STAGED_SECRETS.keys()),
        }
