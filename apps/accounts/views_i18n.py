"""Language-switch wrapper that also persists to User.preferred_language."""

from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import activate

# Django 4.0 removed LANGUAGE_SESSION_KEY; the session key is now `_language`.
LANGUAGE_SESSION_KEY = "_language"
from django.views.decorators.http import require_POST


@require_POST
def set_language_persist(request):
    """Wrap Django's `set_language` to also save to user.preferred_language.

    Posts here from the marketing language switcher (and any other surface that
    wants the persistence side-effect). For anonymous users, behaves exactly
    like Django's set_language (session only). For authenticated users,
    additionally writes the choice to `request.user.preferred_language` so it
    survives logout / new session, and is applied on next login by the
    `apply_preferred_language_on_login` signal.
    """
    next_url = request.POST.get("next") or request.GET.get("next") or "/"
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = "/"

    lang = (request.POST.get("language") or "").strip().lower()
    valid_codes = {c.lower() for c, _name in settings.LANGUAGES}
    if lang in valid_codes:
        request.session[LANGUAGE_SESSION_KEY] = lang
        activate(lang)
        if getattr(request, "user", None) and request.user.is_authenticated:
            try:
                if request.user.preferred_language != lang:
                    request.user.preferred_language = lang
                    request.user.save(update_fields=["preferred_language"])
            except Exception:
                # Preference persistence is best-effort; never block the redirect.
                pass

    response = HttpResponseRedirect(next_url)
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        lang if lang in valid_codes else settings.LANGUAGE_CODE,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        path=settings.LANGUAGE_COOKIE_PATH,
        domain=settings.LANGUAGE_COOKIE_DOMAIN,
        secure=settings.LANGUAGE_COOKIE_SECURE,
        httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
    )
    return response
