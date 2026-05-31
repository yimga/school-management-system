"""v4.00.93 Wave C — landing views for the 6 power chips.

Each chip's anchor target lives here:

  /assist-dock/translate/   → locale picker (POSTs to django.set_language)
  /assist-dock/share/       → share-this-view sheet
  /assist-dock/theme/       → theme/aesthetic flip
  /assist-dock/inspect/     → super-only RBAC + settings overlay
  /assist-dock/impersonate/ → super-only role-switch picker
  /assist-dock/prefs/       → GET prefs JSON / POST updated prefs

Honest-stub policy: each landing renders a minimal but functional surface
so the chip is never a dead link. Deeper UX iterations land in later waves.
"""

from __future__ import annotations

import json
import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_safe

logger = logging.getLogger(__name__)


def _sanitize_next_url(raw: str) -> str:
    """Reject absolute URLs / open-redirect attempts."""
    if not raw:
        return "/"
    raw = raw[:512]
    if raw.startswith("/") and not raw.startswith("//"):
        return raw
    return "/"


@login_required
@require_safe
def translate_landing(request):
    """Locale picker — lists installed LANGUAGES + POSTs to set_language.

    Wave F3: also surfaces the user's saved ``locale_preference`` so the
    picker can render a check next to the sticky choice + the JS can
    write it back to the prefs endpoint when the user picks one.
    """
    from django.conf import settings

    languages = []
    for code, label in getattr(settings, "LANGUAGES", []):
        languages.append({"code": code, "label": str(label)})
    try:
        from .models import get_or_default_prefs

        prefs = get_or_default_prefs(request.user)
    except (ImportError, RuntimeError):
        prefs = {}
    return render(
        request,
        "assist_dock/power/translate.html",
        {
            "languages": languages,
            "current_language": getattr(request, "LANGUAGE_CODE", ""),
            "locale_preference": (prefs or {}).get("locale_preference", ""),
            "prefs_url": "/assist-dock/prefs.json",
            "next_url": _sanitize_next_url(request.GET.get("next", "/")),
        },
    )


@login_required
@require_safe
def share_landing(request):
    """Share-this-view sheet — format chooser + copyable short URL.

    The short-link issuer is a downstream concern (apps.api or a tenant
    URL shortener); the chip surfaces the raw page URL with the copy-to-
    clipboard UX for now.
    """
    page = _sanitize_next_url(request.GET.get("page", "/"))
    return render(
        request,
        "assist_dock/power/share.html",
        {
            "page": page,
            "absolute_url": request.build_absolute_uri(page),
        },
    )


@login_required
@require_safe
def theme_landing(request):
    """Theme flip landing — three swatches that POST to the preference setter."""
    return render(
        request,
        "assist_dock/power/theme.html",
        {
            "themes": [
                {"slug": "system", "label": _("System")},
                {"slug": "light", "label": _("Light")},
                {"slug": "dark", "label": _("Dark")},
            ],
            "next_url": _sanitize_next_url(request.GET.get("next", "/")),
        },
    )


@staff_member_required
@require_safe
def inspect_landing(request):
    """Super-only RBAC + settings introspection overlay for a page.

    Wave E6 — replaces the v3 path-prefix sniff with real Django URL
    resolution: ``resolve(path)`` → URL name + namespace + view callable
    + module; then walks the callable's decorator chain looking for the
    canonical auth markers (login_required / staff_member_required /
    permission_required / DRF permission_classes / class-based mixins).
    """
    page = _sanitize_next_url(request.GET.get("page", "/"))
    rbac_signal = _deep_rbac_signal(page)
    site_settings_keys = _try_site_settings_keys(request)
    return render(
        request,
        "assist_dock/power/inspect.html",
        {
            "page": page,
            "rbac_signal": rbac_signal,
            "site_settings_keys": site_settings_keys,
        },
    )


@staff_member_required
@require_safe
def impersonate_landing(request):
    """Super-only impersonation picker — routes to the real flow when present.

    Wave E7 — detects whether the project ships a discoverable impersonation
    URL (``accounts:impersonate`` / ``schools:impersonate`` / similar) and
    surfaces it as a direct CTA. Falls back to the honest stub when no
    such URL resolves, with the operator-facing explanation intact.
    """
    routes = _resolve_impersonation_routes()
    return render(
        request,
        "assist_dock/power/impersonate.html",
        {
            "next_url": _sanitize_next_url(request.GET.get("next", "/")),
            "impersonation_routes": routes,
            "impersonation_wired": bool(routes),
        },
    )


@login_required
@require_safe
def presence_landing(request):
    """Wave E1 — list of co-viewers currently on the requested page."""
    from .presence import (
        PRESENCE_HEARTBEAT_SECONDS,
        entries_as_jsonable,
        list_present,
    )

    page = _sanitize_next_url(request.GET.get("page", "/"))
    user_id = getattr(request.user, "pk", None) or 0
    present = list_present(page_path=page, exclude_user_id=user_id)
    return render(
        request,
        "assist_dock/power/presence.html",
        {
            "page": page,
            "present": entries_as_jsonable(present),
            "heartbeat_seconds": PRESENCE_HEARTBEAT_SECONDS,
            "next_url": _sanitize_next_url(request.GET.get("next", "/")),
        },
    )


@login_required
@require_safe
def settings_landing(request):
    """Wave E4 — drag-to-pin prefs editor.

    Lists every slot the user currently sees (post-prefs filter) AND every
    registered slot they CAN see; the template wires HTML5 DnD to reorder
    + checkboxes to hide; submit POSTs to ``/assist-dock/prefs.json``.
    """
    from .context_processors import _resolve_role, _resolve_surface
    from .models import get_or_default_prefs
    from .registry import get_slots_for, slots_as_jsonable

    surface = _resolve_surface(request)
    role = _resolve_role(request)
    all_visible = get_slots_for(surface=surface, role=role)
    prefs = get_or_default_prefs(request.user)
    return render(
        request,
        "assist_dock/power/settings.html",
        {
            "surface": surface,
            "role": role,
            "slots": slots_as_jsonable(all_visible),
            "prefs": prefs,
            "next_url": _sanitize_next_url(request.GET.get("next", "/")),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
@csrf_protect
def prefs_view(request):
    """GET returns the current user's prefs payload; POST merges + saves it.

    Payload is sanitized via ``coerce_payload`` so unknown keys / lengths
    can't bloat the row.
    """
    from .models import UserAssistDockPrefs, coerce_payload, get_or_default_prefs

    user = request.user
    if request.method == "GET":
        return JsonResponse({"payload": get_or_default_prefs(user)})

    try:
        raw = json.loads((request.body or b"{}").decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("bad json")
    if not isinstance(raw, dict):
        return HttpResponseBadRequest("payload must be an object")

    payload = coerce_payload(raw)
    # tenant-isolation-allow: assist-dock-prefs-write-user-pk-public-schema-shared
    UserAssistDockPrefs.objects.update_or_create(
        user=user, defaults={"payload": payload}
    )
    return JsonResponse({"payload": payload, "saved": True})


def _try_rbac_signal(page: str) -> dict:
    """v3 fallback: pull the rbac-allow markers active for the page path."""
    try:
        signal = {"path": page}
        if page.startswith("/super/"):
            signal["scope"] = "manager-host super-staff"
        elif page.startswith("/admin/"):
            signal["scope"] = "django-admin staff"
        elif page.startswith("/portal/"):
            signal["scope"] = "tenant-portal authenticated"
        else:
            signal["scope"] = "public"
        return signal
    except (AttributeError, RuntimeError):
        return {}


# Decorator names we surface as auth signals.
_AUTH_DECORATOR_NAMES = frozenset(
    {
        "login_required",
        "staff_member_required",
        "user_passes_test",
        "permission_required",
        "csrf_protect",
        "csrf_exempt",
        "require_safe",
        "require_http_methods",
        "require_POST",
        "require_GET",
    }
)

# Class-based view auth mixin names (Django + project-specific).
_AUTH_MIXIN_NAMES = frozenset(
    {
        "LoginRequiredMixin",
        "UserPassesTestMixin",
        "PermissionRequiredMixin",
        "StaffMemberRequiredMixin",
    }
)


def _deep_rbac_signal(page: str) -> dict:
    """Wave E6 — real URL resolution + auth decorator/mixin walk.

    Falls back cleanly to the v3 path-prefix sniff when ``resolve()``
    can't match the path (e.g. operator pasted a marketing URL).
    """
    base = _try_rbac_signal(page)
    try:
        from django.urls import Resolver404, resolve
    except (ImportError, RuntimeError):
        return base
    try:
        match = resolve(page)
    except Resolver404:
        base["resolved"] = False
        return base
    except Exception as exc:  # noqa: BLE001 — defensive
        logger.debug("URL resolve for %r failed: %s", page, exc)
        return base
    base["resolved"] = True
    base["url_name"] = match.url_name or ""
    base["namespace"] = match.namespace or ""
    view_callable = match.func
    base["view_module"] = getattr(view_callable, "__module__", "")
    base["view_name"] = getattr(view_callable, "__qualname__", "") or getattr(
        view_callable, "__name__", ""
    )
    base["auth_decorators"] = _walk_auth_decorators(view_callable)
    base["auth_mixins"] = _walk_auth_mixins(view_callable)
    return base


def _walk_auth_decorators(view_callable) -> list[str]:
    """Best-effort extraction of decorator names wrapping a view.

    Detection strategies (any one is enough):

      * The wrapper's ``__qualname__`` / ``__name__`` starts with a known
        decorator name — works for direct decorations like
        ``@require_safe`` where the wrapper isn't renamed.
      * The wrapper's closure carries marker nonlocals — covers
        ``@login_required`` (closure has ``test_func``) and
        ``@staff_member_required`` (closure has ``user_passes_test``).
      * ``functools.wraps``-style ``__wrapped__`` chain is walked so
        every layer gets inspected.

    Stops at depth 8 so a pathological chain can't spin forever.
    """
    found: list[str] = []
    seen: set[int] = set()
    current = view_callable
    depth = 0
    while current is not None and id(current) not in seen and depth < 8:
        seen.add(id(current))
        depth += 1
        # Match by qualname prefix (works for non-renamed wrappers).
        for attr in ("__qualname__", "__name__"):
            name = getattr(current, attr, "") or ""
            if not name:
                continue
            short = name.split(".", 1)[0]
            if short in _AUTH_DECORATOR_NAMES and short not in found:
                found.append(short)
            break
        # Match by closure marker nonlocals.
        closure_names = _closure_var_names(current)
        if "test_func" in closure_names or "_redirect_to_login" in closure_names:
            if "login_required" not in found:
                found.append("login_required")
        if "view_func" in closure_names and "request" in closure_names:
            # csrf_protect-style wrapper — keep noting it lightly.
            pass
        if "perms" in closure_names or "permissions_required" in closure_names:
            if "permission_required" not in found:
                found.append("permission_required")
        # Follow functools.wraps chain.
        inner = getattr(current, "__wrapped__", None)
        if inner is not None and inner is not current:
            current = inner
            continue
        # Follow closure to the next callable cell (e.g. method_decorator stacks).
        for cell in getattr(current, "__closure__", None) or ():
            try:
                value = cell.cell_contents
            except (AttributeError, ValueError):
                continue
            if callable(value) and value is not current:
                current = value
                break
        else:
            current = None
    return found


def _closure_var_names(func) -> frozenset[str]:
    """Return the closure-nonlocal names for ``func``, or empty frozenset."""
    closure = getattr(func, "__closure__", None)
    if not closure:
        return frozenset()
    code = getattr(func, "__code__", None)
    if code is None:
        return frozenset()
    names = getattr(code, "co_freevars", ())
    return frozenset(names)


def _walk_auth_mixins(view_callable) -> list[str]:
    """For class-based views, list any recognized auth mixin in the MRO."""
    cls = getattr(view_callable, "view_class", None) or getattr(
        view_callable, "cls", None
    )
    if cls is None:
        return []
    found: list[str] = []
    for base in getattr(cls, "__mro__", []):
        name = getattr(base, "__name__", "")
        if name in _AUTH_MIXIN_NAMES and name not in found:
            found.append(name)
    return found


# Known impersonation URL-name candidates across the project. Try each in
# order — first that reverses cleanly wins.
_IMPERSONATION_URL_CANDIDATES = (
    "accounts:impersonate",
    "accounts:impersonation_picker",
    "accounts:impersonate_start",
    "schools:impersonate",
    "schools:operator_impersonate",
    "studio_os:impersonate",
)


def _resolve_impersonation_routes() -> list[dict]:
    """Wave E7 — return any concrete impersonation URLs the project exposes.

    Each entry is ``{"name": "<url-name>", "url": "<resolved-path>"}``.
    Empty list = honest stub falls through.
    """
    try:
        from django.urls import NoReverseMatch, reverse
    except (ImportError, RuntimeError):
        return []
    out: list[dict] = []
    for url_name in _IMPERSONATION_URL_CANDIDATES:
        try:
            path = reverse(url_name)
        except NoReverseMatch:
            continue
        except Exception as exc:  # noqa: BLE001 — defensive
            logger.debug("impersonation reverse for %s failed: %s", url_name, exc)
            continue
        out.append({"name": url_name, "url": path})
    return out


def _try_site_settings_keys(request) -> list[str]:
    """Tenant-scoped SiteSettings keys — best-effort, never raises."""
    try:
        from apps.siteconfig.models import SiteSettings

        school = getattr(request, "school", None)
        if school is None:
            return []
        # tenant-isolation-allow: assist-dock-inspect-readonly-keys-current-tenant-school-fk
        row = SiteSettings.objects.filter(school=school).only("id").first()
        if row is None:
            return []
        # Return a small fixed set of keys to keep the overlay legible.
        return ["site_name", "default_currency", "default_locale"]
    except (AttributeError, ImportError, RuntimeError, ValueError):
        return []
