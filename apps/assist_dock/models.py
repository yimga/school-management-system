"""v4.00.93 Wave C — per-user assist dock preferences.

Operators can:
  * Reorder chips (drag to pin to primary row)
  * Hide chips they never use
  * Switch dock side (right vs left — RTL friendly)
  * Toggle density (cozy vs compact)
  * Mute the predictive halo

Single ``UserAssistDockPrefs`` row per user, JSON payload. Lives in the
public schema (User does too) so prefs survive a tenant switch.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


_DEFAULT_PAYLOAD: dict = {
    "pinned_order": [],          # ordered slot ids the user has explicitly pinned
    "hidden_slots": [],          # slot ids the user has hidden from this surface
    "density": "cozy",           # "cozy" | "compact"
    "side": "right",             # "right" | "left"
    "halo_enabled": True,        # predictive halo on/off
    "voice_enabled": False,      # opt-in for the voice chip
    "locale_preference": "",     # v4.00.96 Wave F3 — sticky locale across sessions
    "version": 1,                # payload schema version
}


# Validation helpers shared by the model + the prefs view layer.
VALID_DENSITY = frozenset({"cozy", "compact"})
VALID_SIDE = frozenset({"right", "left"})
MAX_PINNED = 12                  # cap to keep the primary row sane
MAX_HIDDEN = 64                  # cap to bound payload size
SLOT_ID_MAX_LEN = 64             # mirror registry contract


def default_prefs_payload() -> dict:
    # Deep copy so callers can mutate freely without touching the module sentinel.
    return {
        "pinned_order": list(_DEFAULT_PAYLOAD["pinned_order"]),
        "hidden_slots": list(_DEFAULT_PAYLOAD["hidden_slots"]),
        "density": _DEFAULT_PAYLOAD["density"],
        "side": _DEFAULT_PAYLOAD["side"],
        "halo_enabled": _DEFAULT_PAYLOAD["halo_enabled"],
        "voice_enabled": _DEFAULT_PAYLOAD["voice_enabled"],
        "locale_preference": _DEFAULT_PAYLOAD["locale_preference"],
        "version": _DEFAULT_PAYLOAD["version"],
    }


# Permissive locale shape — Django LANGUAGE_CODE format ``en`` / ``en-us``.
_LOCALE_PREFERENCE_MAX_LEN = 16
_LOCALE_PREFERENCE_RE = None  # compiled lazily below to keep import cheap


def _validate_locale_preference(value: str) -> str:
    """Return the cleaned locale slug or '' if it doesn't match the shape."""
    if not value:
        return ""
    value = str(value).strip().lower()[:_LOCALE_PREFERENCE_MAX_LEN]
    if not value:
        return ""
    global _LOCALE_PREFERENCE_RE
    if _LOCALE_PREFERENCE_RE is None:
        import re

        _LOCALE_PREFERENCE_RE = re.compile(r"^[a-z]{2,3}(?:[_-][a-z0-9]{2,8})?$")
    return value if _LOCALE_PREFERENCE_RE.match(value) else ""


class UserAssistDockPrefs(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assist_dock_prefs",
    )
    payload = models.JSONField(default=default_prefs_payload, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Assist dock preferences"
        verbose_name_plural = "Assist dock preferences"

    def __str__(self) -> str:  # pragma: no cover - admin only
        return f"AssistDockPrefs(user_id={self.user_id})"


def coerce_payload(raw) -> dict:
    """Sanitize a payload dict — drops unknown keys + clamps lengths.

    Pure function so tests + view layers can both call it without an ORM
    round-trip. Returns a new dict; never mutates the input.
    """
    payload = default_prefs_payload()
    if not isinstance(raw, dict):
        return payload
    pinned = raw.get("pinned_order")
    if isinstance(pinned, (list, tuple)):
        payload["pinned_order"] = [
            str(x)[:SLOT_ID_MAX_LEN] for x in pinned[:MAX_PINNED] if x
        ]
    hidden = raw.get("hidden_slots")
    if isinstance(hidden, (list, tuple)):
        payload["hidden_slots"] = [
            str(x)[:SLOT_ID_MAX_LEN] for x in hidden[:MAX_HIDDEN] if x
        ]
    density = raw.get("density")
    if density in VALID_DENSITY:
        payload["density"] = density
    side = raw.get("side")
    if side in VALID_SIDE:
        payload["side"] = side
    payload["halo_enabled"] = bool(raw.get("halo_enabled", True))
    payload["voice_enabled"] = bool(raw.get("voice_enabled", False))
    payload["locale_preference"] = _validate_locale_preference(
        raw.get("locale_preference", "")
    )
    return payload


def get_or_default_prefs(user) -> dict:
    """Return the prefs payload for ``user`` (defaults if no row yet).

    Defensive: returns the default payload if the user is anonymous, if
    the DB is unreachable, or if the row's payload is malformed. The
    catch is broad on purpose — the assist dock context processor runs
    on every page render and must NEVER raise into the template chain.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return default_prefs_payload()
    try:
        # tenant-isolation-allow: assist-dock-prefs-user-pk-public-schema-shared
        row = UserAssistDockPrefs.objects.filter(user_id=user.pk).only("payload").first()
    except Exception:  # noqa: BLE001 — context processor must never raise
        return default_prefs_payload()
    if row is None:
        return default_prefs_payload()
    return coerce_payload(row.payload)


class InsightRecord(models.Model):
    """v4.00.95 Wave E2 — durable + cross-worker copilot insight.

    Mirror of the in-process ``Insight`` ring. Push paths write to BOTH
    layers; reads consult memory first (fast path), then fall back to
    DB (cross-worker / restart-survival path). Sweeper drops expired rows.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assist_dock_insights",
    )
    insight_id = models.CharField(max_length=128)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    level = models.CharField(max_length=16, default="info")
    page_path = models.CharField(max_length=256, blank=True, default="")
    cta_label = models.CharField(max_length=120, blank=True, default="")
    cta_href = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Assist dock insight"
        verbose_name_plural = "Assist dock insights"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "insight_id"),
                name="ad_uniq_user_insight_id",
            ),
        ]
        indexes = [
            models.Index(
                fields=("user", "expires_at"),
                name="ad_insight_user_exp_idx",
            ),
            models.Index(
                fields=("user", "page_path"),
                name="ad_insight_user_page_idx",
            ),
        ]


class PresencePing(models.Model):
    """v4.00.96 Wave F1 — durable + cross-worker presence row.

    Mirror of the in-process ``presence`` ring. Heartbeat writes to BOTH
    layers; ``list_present`` consults memory first (fast path) and the DB
    second (cross-worker visibility). Single row per ``(user, page_path)``
    via the unique constraint; conflict path updates ``last_seen``.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assist_dock_presence_pings",
    )
    page_path = models.CharField(max_length=256)
    display_name = models.CharField(max_length=80, blank=True, default="")
    avatar_url = models.CharField(max_length=512, blank=True, default="")
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Assist dock presence ping"
        verbose_name_plural = "Assist dock presence pings"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "page_path"),
                name="ad_uniq_user_page",
            ),
        ]
        indexes = [
            models.Index(
                fields=("page_path", "last_seen"),
                name="ad_presence_page_last_idx",
            ),
        ]


class AssistDockShortLink(models.Model):
    """v4.00.95 Wave E5 — 24h short-link for the share chip.

    Token is a 22-char urlsafe random string; lookup is by ``token``.
    Resolver redirects to ``target_url`` only when ``expires_at`` is in
    the future; otherwise 410.
    """

    token = models.CharField(max_length=32, unique=True, db_index=True)
    target_url = models.CharField(max_length=2048)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assist_dock_short_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    hits = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Assist dock short link"
        verbose_name_plural = "Assist dock short links"
        indexes = [
            models.Index(
                fields=("created_by", "expires_at"),
                name="ad_shortlink_user_exp_idx",
            ),
        ]


class AssistDockShortLinkRecipient(models.Model):
    """v4.00.96 Wave F4 — one row per recipient the operator emailed.

    Surfaces who got the link + when, so the operator can later see
    receipts in a "your shares" view. The actual email send is
    best-effort through Django's email backend; sending failures land
    here as ``send_status``.
    """

    short_link = models.ForeignKey(
        "AssistDockShortLink",
        on_delete=models.CASCADE,
        related_name="recipients",
    )
    address = models.CharField(max_length=320)            # RFC 5321 max
    sent_at = models.DateTimeField(auto_now_add=True)
    send_status = models.CharField(max_length=32, default="queued")
    notes = models.CharField(max_length=256, blank=True, default="")

    class Meta:
        verbose_name = "Assist dock short link recipient"
        verbose_name_plural = "Assist dock short link recipients"
        indexes = [
            models.Index(
                fields=("short_link", "sent_at"),
                name="ad_shortlink_recip_idx",
            ),
        ]


# v4.00.97 Wave G2 — re-export impersonation models so Django discovers them.
from .impersonation import (  # noqa: E402, F401
    ImpersonationAuditEvent,
    ImpersonationAuditEventType,
    ImpersonationGrant,
    ImpersonationGrantStatus,
    ImpersonationSession,
)


def apply_prefs_to_slots(slots, payload):
    """Reorder + filter ``slots`` per the user's preference payload.

    Slots in ``hidden_slots`` are dropped. Slots in ``pinned_order`` are
    sorted in that order and placed before the remaining slots. Order
    within the unpinned tail comes from the slot's own ``order`` field.
    Pure function; never mutates the input list.
    """
    if not slots:
        return []
    hidden = set(payload.get("hidden_slots") or [])
    pinned_order = list(payload.get("pinned_order") or [])
    pinned_rank = {sid: idx for idx, sid in enumerate(pinned_order)}

    pinned, rest = [], []
    for slot in slots:
        if slot.id in hidden:
            continue
        if slot.id in pinned_rank:
            pinned.append(slot)
        else:
            rest.append(slot)
    pinned.sort(key=lambda s: pinned_rank.get(s.id, 99999))
    rest.sort(key=lambda s: (s.order, s.id))
    return pinned + rest
