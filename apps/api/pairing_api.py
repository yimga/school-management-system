"""Cloud endpoints for box pairing: ``start`` and ``poll``.

Both are deliberately ANONYMOUS, which deserves a straight answer rather than a
disclaimer. A box that has never been paired holds no credential — that is the whole
problem pairing exists to solve — so there is nothing for it to authenticate with.
What an anonymous caller can actually achieve here is bounded:

  * ``start`` creates a row in a review queue and returns a code that does nothing
    until a signed-in admin of the named school approves it. Flooding it is a nuisance,
    not an escalation, and it is rate-limited.
  * ``poll`` requires the ``poll_secret`` returned exactly once by ``start``. A caller
    without it gets the same answer as a caller naming a request that does not exist,
    so the endpoint cannot be used to enumerate ids.

The credential is minted inside ``poll`` and exists only in that response. Nothing here
writes it anywhere.
"""
from __future__ import annotations

import json
import logging

from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sync_engine.pairing_service import collect_pairing, start_pairing

logger = logging.getLogger(__name__)

# A box polls every few seconds while a human walks to a laptop; a flood of starts is
# something else. The two limits differ because the two behaviours differ.
START_RATE_PER_HOUR = 20
POLL_RATE_PER_MINUTE = 60


def _client_ip(request) -> str:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return forwarded or (request.META.get("REMOTE_ADDR") or "").strip()


def _rate_limited(bucket: str, ip: str, *, limit: int, window_seconds: int) -> bool:
    """Fixed-window counter. Best-effort: a cache outage must not close the door.

    Pairing is the path a school uses to come online for the first time. A rate
    limiter that fails CLOSED would turn a Redis blip into "no new school can be
    installed today", which is a worse outcome than the abuse it prevents.
    """
    if not ip:
        return False
    key = f"rmc:pairing:{bucket}:{ip}"
    try:
        current = cache.get_or_set(key, 0, window_seconds)
        try:
            current = cache.incr(key)
        except ValueError:
            # Key expired between get_or_set and incr — start the window again.
            cache.set(key, 1, window_seconds)
            current = 1
        return int(current) > limit
    except Exception:  # noqa: BLE001 — never fail closed on a cache problem
        logger.debug("pairing rate-limit check failed for %s", bucket, exc_info=True)
        return False


def _body(request) -> dict:
    if isinstance(getattr(request, "data", None), dict):
        return request.data
    try:
        return json.loads((request.body or b"{}").decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}


@method_decorator(csrf_exempt, name="dispatch")
class PairingStartView(APIView):
    """POST — a box asks to be adopted. Returns the code it should DISPLAY."""

    authentication_classes: list = []
    permission_classes = [AllowAny]  # rbac-allow: unpaired-box-holds-no-credential-by-definition

    @extend_schema(
        operation_id="sync_pairing_start",
        description=(
            "Open a pairing request for an unpaired edge box. Returns a short "
            "user_code for the box to display and a one-time poll_secret the box "
            "must keep. Neither grants access; a signed-in admin of the named "
            "school must approve before a credential is issued."
        ),
        request=None,
        responses={200: None, 429: None},
    )
    def post(self, request):
        ip = _client_ip(request)
        if _rate_limited("start", ip, limit=START_RATE_PER_HOUR, window_seconds=3600):
            return Response(
                {"ok": False, "error": "rate_limited"},
                status=429,
            )
        payload = _body(request)
        result = start_pairing(
            claimed_slug=str(payload.get("school_slug") or "")[:100],
            device_id=str(payload.get("device_id") or "")[:128],
            box_label=str(payload.get("box_label") or "")[:120],
            box_hostname=str(payload.get("hostname") or "")[:253],
            box_ip=ip or None,
            box_version=str(payload.get("version") or "")[:64],
        )
        # poll_interval tells the box how often to come back, so the cadence is the
        # cloud's to tune later without shipping a new box image.
        result["poll_interval_seconds"] = 5
        return Response(result, status=200)


@method_decorator(csrf_exempt, name="dispatch")
class PairingPollView(APIView):
    """POST — 'am I approved yet?', and collect the credential exactly once."""

    authentication_classes: list = []
    permission_classes = [AllowAny]  # rbac-allow: authenticated-by-the-one-time-poll-secret-not-a-session

    @extend_schema(
        operation_id="sync_pairing_poll",
        description=(
            "Check whether a pairing request has been approved. When it has, this "
            "call returns the machine credential ONCE and marks the request "
            "redeemed. Requires the poll_secret issued by sync_pairing_start."
        ),
        request=None,
        responses={200: None, 400: None, 429: None},
    )
    def post(self, request):
        ip = _client_ip(request)
        if _rate_limited("poll", ip, limit=POLL_RATE_PER_MINUTE, window_seconds=60):
            return Response({"ok": False, "error": "rate_limited"}, status=429)
        payload = _body(request)
        request_id = str(payload.get("request_id") or "").strip()
        poll_secret = str(payload.get("poll_secret") or "")
        if not request_id or not poll_secret:
            return Response(
                {"ok": False, "status": "unknown", "error": "missing_credentials"},
                status=400,
            )
        try:
            result = collect_pairing(request_id=request_id, poll_secret=poll_secret)
        except (ValueError, TypeError):
            # A malformed uuid is an unknown request, not a server error.
            return Response(
                {"ok": False, "status": "unknown", "error": "unknown_request"},
                status=200,
            )
        # Deliberately 200 for every protocol outcome including refusal: "pending",
        # "denied" and "expired" are answers, not transport failures, and a box that
        # treats a 4xx as "the network is broken" would retry the wrong thing.
        return Response(result, status=200)


__all__ = ["PairingPollView", "PairingStartView"]
