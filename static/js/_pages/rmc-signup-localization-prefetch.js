/**
 * Warm-cache /api/v1/localization/<cc>/ packs for offline-first signup flows.
 *
 * Reads ``prefetch_countries`` from #page-data-rmc-signup-localization and
 * fires background GETs (service worker stale-while-revalidate handles cache).
 */
(function () {
  "use strict";

  function readBootstrap() {
    var node = document.getElementById("page-data-rmc-signup-localization");
    if (!node) return {};
    try {
      return JSON.parse(node.textContent || "{}") || {};
    } catch (_e) {
      return {};
    }
  }

  function resolveLocalizationUrl(code, boot) {
    if (window.RMCPlatformSurface && window.RMCPlatformSurface.localizationUrl) {
      var fromSurface = window.RMCPlatformSurface.localizationUrl(code);
      if (fromSurface) return fromSurface;
    }
    var pattern = boot.urls && boot.urls.localization_country;
    if (!pattern) return "";
    return String(pattern).replace(
      "{country_code}",
      encodeURIComponent(code || "")
    );
  }

  function prefetch() {
    var boot = readBootstrap();
    var codes = boot.prefetch_countries;
    if (!Array.isArray(codes) || !codes.length) return;
    codes.forEach(function (cc) {
      var url = resolveLocalizationUrl(cc, boot);
      if (!url) return;
      fetch(url, { credentials: "same-origin", cache: "force-cache" }).catch(
        function () {
          /* offline / anonymous — SW or next navigation may still serve cache */
        }
      );
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", prefetch, { once: true });
  } else {
    prefetch();
  }
})();
