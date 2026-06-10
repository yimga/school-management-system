"""Canonical return navigation after mutations (delete, save, back, offboard)."""

from __future__ import annotations

from urllib.parse import urlencode, urlparse

from django.http import HttpResponse, HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme

DEFAULT_BLOCKED_PATH_FRAGMENTS = (
    "/delete/",
    "/confirm-delete/",
    "/offboard/",
    "/confirm/",
    "/edit/",
    "/add/",
    "/create/",
)


def _is_safe_url(request, url: str) -> bool:
    value = str(url or "").strip()
    if not value:
        return False
    return url_has_allowed_host_and_scheme(
        url=value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )


def _path_blocked(path: str, fragments: tuple[str, ...]) -> bool:
    lower = (path or "").lower()
    return any(fragment in lower for fragment in fragments)


def _candidate_from_request(request, *, post: bool = True, get: bool = True) -> str:
    if post:
        for key in ("next", "return_url"):
            value = (request.POST.get(key) or "").strip()
            if value:
                return value
    if get:
        value = (request.GET.get("next") or request.GET.get("return_url") or "").strip()
        if value:
            return value
    return ""


def resolve_return_url(
    request,
    fallback: str,
    *,
    candidate: str | None = None,
    list_url: str | None = None,
    block_path_fragments: tuple[str, ...] = DEFAULT_BLOCKED_PATH_FRAGMENTS,
    allow_referer: bool = True,
    prefer_list_over_referer: bool = False,
) -> str:
    """Pick a safe local URL to land on after a mutation.

    Priority (save/back): explicit next → safe referer → list_url → fallback.
    Priority (destructive): explicit next → list_url → fallback (referer skipped).
    """
    safe_fallback = fallback if _is_safe_url(request, fallback) else "/"
    safe_list = list_url if list_url and _is_safe_url(request, list_url) else ""

    for raw in (
        candidate,
        _candidate_from_request(request),
    ):
        value = str(raw or "").strip()
        if not value or not _is_safe_url(request, value):
            continue
        parsed = urlparse(value)
        if _path_blocked(parsed.path, block_path_fragments):
            continue
        return value

    if prefer_list_over_referer:
        if safe_list:
            return safe_list
        return safe_fallback

    if allow_referer:
        referer = (request.META.get("HTTP_REFERER") or "").strip()
        if referer and _is_safe_url(request, referer):
            parsed = urlparse(referer)
            if not _path_blocked(parsed.path, block_path_fragments):
                return referer

    if safe_list:
        return safe_list
    return safe_fallback


def _mutation_response(request, url: str):
    if (request.headers.get("HX-Request") or "").lower() == "true":
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return HttpResponseRedirect(url)


def redirect_after_mutation(
    request,
    fallback: str,
    *,
    candidate: str | None = None,
    list_url: str | None = None,
    prefer_list_over_referer: bool = False,
):
    """Redirect (or HTMX HX-Redirect) to the resolved return URL."""
    url = resolve_return_url(
        request,
        fallback,
        candidate=candidate,
        list_url=list_url,
        prefer_list_over_referer=prefer_list_over_referer,
    )
    return _mutation_response(request, url)


def redirect_after_delete(
    request,
    fallback: str,
    *,
    candidate: str | None = None,
    list_url: str | None = None,
):
    """After delete/offboard/purge — prefer list hub over detail referer."""
    return redirect_after_mutation(
        request,
        fallback,
        candidate=candidate,
        list_url=list_url,
        prefer_list_over_referer=True,
    )


def redirect_after_save(
    request,
    fallback: str,
    *,
    candidate: str | None = None,
    list_url: str | None = None,
):
    """After create/update save — honor filters via next or referer."""
    return redirect_after_mutation(
        request,
        fallback,
        candidate=candidate,
        list_url=list_url,
        prefer_list_over_referer=False,
    )


def redirect_after_detail_mutation(
    request,
    detail_url: str,
    *,
    candidate: str | None = None,
    list_url: str | None = None,
):
    """After in-place detail mutations (revoke sessions, suspend) — stay on detail."""
    return redirect_after_mutation(
        request,
        detail_url,
        candidate=candidate,
        list_url=list_url or detail_url,
        prefer_list_over_referer=False,
    )


def append_return_query(url: str, request, fallback: str) -> str:
    """Append ``?next=`` when linking to a delete-confirm or mutation page."""
    return_url = resolve_return_url(request, fallback, list_url=fallback)
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'next': return_url})}"


def mutation_return_url(request, fallback: str, *, list_url: str | None = None) -> str:
    """Template helper: resolved return URL for hidden ``next`` fields and back links."""
    return resolve_return_url(request, fallback, list_url=list_url or fallback)


def safe_next_url(request, candidate: str | None, fallback: str = "") -> str:
    """Validate a single candidate URL (legacy ``_safe_next_url`` replacement)."""
    value = str(candidate or "").strip()
    if value and _is_safe_url(request, value):
        return value
    fb = str(fallback or "").strip()
    if fb and _is_safe_url(request, fb):
        return fb
    return fb or "/"
