/**
 * Reads page-data-rmc-platform-surface (platform_surface_config SOT).
 * All product API paths should resolve via RMCPlatformSurface.url(key).
 */
(function (global) {
  "use strict";

  var cached = null;

  function readPayload() {
    if (cached !== null) return cached;
    var node = document.getElementById("page-data-rmc-platform-surface");
    if (!node) {
      cached = {};
      return cached;
    }
    try {
      cached = JSON.parse(node.textContent || "{}");
    } catch (_e) {
      cached = {};
    }
    return cached;
  }

  function url(key, fallback) {
    var urls = readPayload().urls || {};
    var resolved = String(urls[key] || "").trim();
    if (resolved) return resolved;
    return fallback ? String(fallback) : "";
  }

  function localizationUrl(countryCode) {
    var pattern = url("localization_country");
    if (!pattern) return "";
    return pattern.replace("{country_code}", encodeURIComponent(countryCode || ""));
  }

  function templated(key, replacements) {
    var pattern = url(key);
    if (!pattern) return "";
    var out = pattern;
    replacements = replacements || {};
    Object.keys(replacements).forEach(function (token) {
      out = out.split("{" + token + "}").join(encodeURIComponent(replacements[token] || ""));
    });
    return out;
  }

  global.RMCPlatformSurface = {
    read: readPayload,
    url: url,
    localizationUrl: localizationUrl,
    templated: templated,
    offline: function () {
      return global.SMS_OFFLINE_CONFIG || readPayload().offline || {};
    },
  };
})(typeof window !== "undefined" ? window : this);
