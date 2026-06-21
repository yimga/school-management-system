"""
Serve the platform service worker from ``/sw.js`` with full-site scope.

Static-file hosting under ``/static/js/`` caps SW scope at ``/static/js/``, which
prevents navigation + CSS interception — the root cause of stale post-deploy UI
when hashed assets update but the SW never controls page loads.
"""

from __future__ import annotations

from pathlib import Path

from django.contrib.staticfiles import finders
from django.http import HttpResponse, JsonResponse
from django.templatetags.static import static as django_static
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.siteconfig.deploy_meta import read_service_worker_cache_version

_SW_PRECACHE_PATHS = (
    "css/design-tokens.css",
    "css/rmc-wizard.css",
    "css/rmc-wizard-engine.css",
    "css/rmc-wizard-assist.css",
    "css/rmc-setup-surface.css",
    "css/rmc-tenant-canvas-100x.css",
    "css/rmc-operator-tools-tray.css",
    "css/dashboard-responsive.css",
    "css/reduce-motion-low-power.css",
    "js/dashboard-layout.js",
    "js/vendor/dexie.min.js",
    "js/offline-db.js",
    "js/offline-crypto-wrapper.js",
    "js/rmc-wizard-offline-intake.js",
    "js/rmc-plickers-card-sweep.js",
    "js/form-draft-save.js",
    "js/sync-manager.js",
    "js/low-power.js",
    "js/offline-status-bar.js",
    "js/auto-pilot.js",
    "js/rmc-lexicon.js",
    "js/rmc-friction.js",
    "images/logo.png",
    "manifest.json",
)


@require_GET
@never_cache
def service_worker_script(request):
    """Return service-worker.js with ``Service-Worker-Allowed: /``."""
    del request
    abs_path = finders.find("js/service-worker.js")
    if not abs_path:
        return HttpResponse(
            "// RunMyCampus service worker unavailable\n",
            status=404,
            content_type="application/javascript; charset=utf-8",
        )
    try:
        body = Path(abs_path).read_bytes()
    except OSError:
        return HttpResponse(
            "// RunMyCampus service worker unreadable\n",
            status=503,
            content_type="application/javascript; charset=utf-8",
        )
    response = HttpResponse(body, content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["CDN-Cache-Control"] = "no-store"
    return response


@require_GET
@never_cache
def service_worker_asset_manifest(request):
    """JSON manifest of hashed static URLs for SW install-time precache."""
    del request
    assets = ["/offline/"]
    for rel_path in _SW_PRECACHE_PATHS:
        try:
            assets.append(django_static(rel_path))
        except (OSError, RuntimeError, TypeError, ValueError):
            assets.append(f"/static/{rel_path}")
    return JsonResponse(
        {
            "version": read_service_worker_cache_version(),
            "assets": assets,
        }
    )
