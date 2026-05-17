"""Tour analytics API — records FeatureUsageEvent for start / complete / skip."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .feature_usage import track_event

_ALLOWED = frozenset({"start", "complete", "skip", "step"})


@login_required
@require_POST
def tour_analytics_api(request):
    """
    POST event=start|complete|skip|step&context=backend_dashboard
    Records tour:{event} and tour:{context}:{event} when context is set.
    """
    event = (request.POST.get("event") or "").strip().lower()
    context = (request.POST.get("context") or "").strip()
    if event not in _ALLOWED:
        return JsonResponse({"ok": False, "error": "invalid_event"}, status=400)
    school = getattr(request, "school", None)
    user = request.user if getattr(request.user, "is_authenticated", False) else None
    track_event(f"tour:{event}", school=school, user=user)
    if context:
        track_event(f"tour:{context}:{event}", school=school, user=user)
    return JsonResponse({"ok": True})
