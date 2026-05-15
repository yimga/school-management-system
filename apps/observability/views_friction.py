"""Wave B — G5: friction-event ingestion endpoint.

POST /api/observability/friction/  (CSRF-exempt, same-origin)

Body:
    {
      "view_name": "portal:grades.entry",
      "kind": "validation_retry",
      "payload": { "field_names": ["score"], "retry_count": 3 }
    }

Behaviour:
    Upsert (user, school, view_name, kind, today-UTC) -> increment count.

Throttle: the endpoint trusts the browser-side recorder's debounce, but
adds a defensive **per-rollup-row** rate limit — if more than
``MAX_INCREMENTS_PER_HOUR`` raw events arrive for the same rollup in one
hour, further increments are silently absorbed (still 200) so a misbehaving
recorder cannot inflate the count.
"""

from __future__ import annotations

import json
import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.observability.models_friction import (
    FRICTION_KIND_CODES,
    FrictionEvent,
)

logger = logging.getLogger(__name__)

MAX_INCREMENTS_PER_HOUR = 20
MAX_PAYLOAD_BYTES = 4096  # magic-number-allow: explicit byte ceiling in named module constant


def _safe_payload(raw: object) -> dict:
    """Trim incoming payload to a sane size and shape."""
    if not isinstance(raw, dict):
        return {}
    encoded = json.dumps(raw, separators=(",", ":"), default=str)
    if len(encoded) > MAX_PAYLOAD_BYTES:
        # Keep keys but drop values to preserve diagnostic signal cheaply.
        return {k: "<truncated>" for k in list(raw.keys())[:16]}
    return raw


@csrf_exempt
@require_http_methods(["POST"])
def ingest_friction_event(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated and not getattr(request, "school", None):
        # Anonymous and untenanted — nothing actionable to do with this signal.
        return JsonResponse({"ok": True, "ignored": "no actor"}, status=200)

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    view_name = str(body.get("view_name") or "").strip()[:200]
    kind = str(body.get("kind") or "").strip()
    if not view_name or kind not in FRICTION_KIND_CODES:
        return JsonResponse({"ok": False, "error": "invalid_fields"}, status=400)

    payload = _safe_payload(body.get("payload"))

    user = request.user if getattr(request.user, "is_authenticated", False) else None
    school = getattr(request, "school", None)
    today = timezone.now().date()

    obj, created = FrictionEvent.objects.update_or_create(
        user=user,
        school=school,
        view_name=view_name,
        kind=kind,
        utc_day=today,
        defaults={"last_payload": payload},
    )
    if not created:
        # Hard ceiling on increments per rollup-row-per-hour.
        recent_window = timezone.now() - timezone.timedelta(hours=1)
        if obj.last_seen and obj.last_seen >= recent_window and obj.count >= MAX_INCREMENTS_PER_HOUR:
            return JsonResponse({"ok": True, "absorbed": True, "count": obj.count}, status=200)
        # tenant-isolation-allow: pk lookup is globally unique; obj was just fetched via get_or_create above
        FrictionEvent.objects.filter(pk=obj.pk).update(count=models_f_inc(obj))

    return JsonResponse({"ok": True, "id": obj.pk, "created": created}, status=200 if not created else 201)


def models_f_inc(obj: FrictionEvent) -> object:
    """Return an F() expression incrementing count.

    Wrapped so this view file does not import django.db.models.F at module
    import time (keeps cold-start small) and so tests can inspect it.
    """
    from django.db.models import F

    return F("count") + 1
