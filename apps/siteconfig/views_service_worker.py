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
    "js/rmc-reconnect-rehydrate.js",
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


# Self-contained reset page. Built as a string and served via HttpResponse (NOT
# render()) so it never runs the shell context processors — several of those
# require an authenticated tenant request and 500 for the anonymous hit this page
# is designed to serve. No shell + no SW registration, so it cannot re-register
# the worker it just removed. ``__CSP_NONCE__`` is swapped for the per-request CSP
# nonce so the inline script is allowed by the strict CSP header.
_SW_RESET_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>Resetting the app...</title>
</head>
<body>
  <main style="max-width: 36rem; margin: 4rem auto; padding: 0 1.25rem; line-height: 1.6;">
    <h1>Resetting the app...</h1>
    <p data-rmc-sw-reset-status>Clearing cached service workers and offline data. This page will reload automatically.</p>
    <p>If it doesn't, <a href="/" data-rmc-sw-reset-home>tap here to continue</a>.</p>
    <noscript><p>JavaScript is disabled. Open your browser's site settings for this site and choose
    "Clear site data" / "Unregister service workers", then reload.</p></noscript>
  </main>
  <script nonce="__CSP_NONCE__">
  (function () {
    "use strict";
    function destination() {
      try {
        var next = new URLSearchParams(window.location.search).get("next");
        if (next && next.charAt(0) === "/" && next.charAt(1) !== "/") { return next; }
      } catch (e) {}
      return "/";
    }
    function done() {
      var s = document.querySelector("[data-rmc-sw-reset-status]");
      if (s) { s.textContent = "Done. Reloading the latest version..."; }
      var dest = destination();
      var sep = dest.indexOf("?") === -1 ? "?" : "&";
      window.location.replace(dest + sep + "rmc_fresh=" + Date.now());
    }
    var tasks = [];
    try {
      if ("serviceWorker" in navigator) {
        tasks.push(navigator.serviceWorker.getRegistrations().then(function (rs) {
          return Promise.all(rs.map(function (r) { return r.unregister(); }));
        }));
      }
      if (window.caches && typeof caches.keys === "function") {
        tasks.push(caches.keys().then(function (ks) {
          return Promise.all(ks.map(function (k) { return caches.delete(k); }));
        }));
      }
    } catch (e) {}
    var safety = window.setTimeout(done, 4000);
    Promise.all(tasks).catch(function () {}).then(function () { window.clearTimeout(safety); done(); });
  })();
  </script>
</body>
</html>
"""


@require_GET
@never_cache
def service_worker_reset(request):
    """One-click escape hatch for a browser stuck on a stale service worker.

    Serves a minimal standalone page (no shell, no SW registration) whose script
    unregisters every service worker for this origin and deletes every Cache
    Storage bucket, then reloads. A normal hard-refresh cannot do this — it
    bypasses the SW for one request but never unregisters it, which is why a
    cache-first worker keeps serving stale post-deploy HTML/CSS/JS for days.

    Public + no-cache: a new URL has nothing cached against it, so even a stale
    cache-first worker fetches this page fresh from the network.
    """
    nonce = getattr(request, "csp_nonce", "") or ""
    html = _SW_RESET_HTML.replace("__CSP_NONCE__", nonce)
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
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
