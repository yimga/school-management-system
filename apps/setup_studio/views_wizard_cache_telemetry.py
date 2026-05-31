"""Best-effort wizard localStorage cache telemetry (browser beacon)."""

from __future__ import annotations

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.setup_studio import wizard_telemetry

_ALLOWED_EVENTS = frozenset(
    {"quota_exceeded", "schema_mismatch", "restored", "cleared"}
)


@csrf_exempt
@require_POST
def wizard_cache_telemetry(request):
    wizard_key = (request.POST.get("wizard_key") or "")[:64]
    event = (request.POST.get("event") or "")[:32]
    if wizard_key and event in _ALLOWED_EVENTS:
        wizard_telemetry.emit_state_cache_event(wizard_key, event)
    return HttpResponse(status=204)
