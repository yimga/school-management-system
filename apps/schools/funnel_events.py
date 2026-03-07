"""
Wave 4: Marketing conversion funnel event recording.
Visit -> discovery -> signup -> activation. Used by marketing_landing, discovery, signup, onboarding.
"""
from django.contrib.sessions.backends.base import SessionBase

from apps.schools.models import MarketingFunnelEvent


def _utm_from_request(request) -> tuple[str, str]:
    """Return (utm_source, utm_medium) from request GET, truncated to 128 chars."""
    get = getattr(request, "GET", None) or {}
    src = (get.get("utm_source") or "")[:128]
    med = (get.get("utm_medium") or "")[:128]
    return (src, med)


def record_marketing_funnel_event(event_type: str, request) -> None:
    """Record a funnel event (visit, discovery, signup, activation). No-op if event_type invalid.
    Captures utm_source and utm_medium from request.GET when present."""
    if event_type not in ("visit", "discovery", "signup", "activation"):
        return
    session_key = getattr(request.session, "session_key", None) or ""
    if session_key is None:
        session_key = ""
    utm_source, utm_medium = _utm_from_request(request)
    try:
        MarketingFunnelEvent.objects.create(
            event_type=event_type,
            session_key=session_key,
            utm_source=utm_source,
            utm_medium=utm_medium,
        )
    except Exception:
        pass
