"""Where the CLOUD's sync API lives, in one place.

The box builds ABSOLUTE urls against another deployment, so it cannot just
``reverse()`` and be done. ``reverse()`` answers about the urlconf *this*
process is running, and the box reaches these endpoints from a management
command / Celery task, which resolves against ``ROOT_URLCONF`` rather than the
host-switched tenant urlconf a request would get. Every call site therefore
carried a literal fallback path for when reverse fails.

All seven of those fallbacks were wrong. They named ``/api/v1/sync/...`` while
``apps.api.urls`` -- which is where every ``sync-*`` route is declared -- is
mounted at ``api/`` by both ``config/urls.py`` and ``config/tenant_urls.py``.
``/api/v1/`` is a different module (``apps.api.urls_v1``) that carries no sync
routes at all. So the box asked the cloud for a path that exists on no urlconf,
Django fell through to the tenant catch-all, and the operator saw:

    pull rejected (HTTP 404): <!doctype html> ... data-rmc-premium-shell="tenant"

-- a 404 with a page of HTML in it, whose own hint blamed
``RMC_EDGE_OPERATOR_BASE`` or "an older build". The base was fine and the build
was current; the path was never right.

Keeping the literals here rather than at five call sites is the point:
``test_cloud_endpoints`` asserts each one equals ``reverse()`` of its name, so
a route that moves breaks a test instead of a customer's sync.
"""
from __future__ import annotations

from django.urls import NoReverseMatch, reverse

# url name -> absolute path on the cloud.
#
# Each value is the mount prefix ("/api/") plus the route as declared in
# apps/api/urls.py. Do not hand-edit one half of a pair: the test reverses the
# name and compares, so the urlconf is the authority and this is the mirror.
CLOUD_SYNC_PATHS: dict[str, str] = {
    "api:sync-bundle-upload": "/api/sync/bundle/upload/",
    "api:sync-bundle-download": "/api/sync/bundle/download/",
    "api:sync-bundle-receipt": "/api/sync/bundle/receipt/",
    "api:sync-changes-feed": "/api/sync/changes/",
    "api:sync-file-manifest": "/api/sync/files/manifest/",
    "api:sync-file-chunk": "/api/sync/files/chunk/",
    "api:sync-pair-start": "/api/sync/pair/start/",
    "api:sync-pair-poll": "/api/sync/pair/poll/",
}


def cloud_path(url_name: str) -> str:
    """Path for one cloud sync endpoint.

    Prefers the live urlconf so a deployment that genuinely remounts the API
    still works; falls back to the pinned literal when this process's urlconf
    cannot reverse the name (management command, Celery worker, or a box whose
    host-split urlconf does not carry the API).
    """
    try:
        return reverse(url_name)
    except NoReverseMatch:
        try:
            return CLOUD_SYNC_PATHS[url_name]
        except KeyError:
            # An unknown name is a programming error, not a runtime condition.
            # Failing loudly beats silently building a url that 404s into HTML.
            raise ValueError(f"unknown cloud sync endpoint: {url_name}") from None


def cloud_endpoint(base: str, url_name: str) -> str:
    """Absolute url on the cloud for one sync endpoint."""
    return (base or "").rstrip("/") + cloud_path(url_name)


__all__ = ["CLOUD_SYNC_PATHS", "cloud_path", "cloud_endpoint"]
