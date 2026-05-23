/**
 * rmc-non-gregorian-display.js
 *
 * v3.62.7 (2026-05-22) — Wave 4 local-first.
 *
 * Display-only layer that converts a Gregorian date to the country-local
 * calendar representation for rendering. Storage stays ISO-8601 Gregorian
 * everywhere; this layer just produces a parallel display string when
 * the user's country uses a non-Gregorian primary calendar.
 *
 * Currently supports (via JS Intl.DateTimeFormat where browsers ship the
 * calendar — Chrome, Edge, Safari, Firefox all do as of 2024+):
 *
 *   - islamic-umalqura     SA / AE / OM / KW / QA / BH / YE / JO / etc.
 *   - islamic              EG / MA / TN / DZ / LY / SD / fallback
 *   - hebrew               IL
 *   - persian              IR / AF
 *   - ethiopic             ET / ER
 *   - chinese              CN / TW / HK / MO  (overlay; default still Gregorian)
 *   - japanese             JP (era-aware)
 *
 * Usage:
 *
 *     // Element with data-rmc-non-gregorian-date="2026-05-22" -- the JS
 *     // replaces the textContent with the country-local rendering once
 *     // bootstrap has resolved the user's country.
 *
 * Or programmatically:
 *
 *     RMCNonGregorian.format(new Date(), "SA")
 *     // -> "5 ذو القعدة 1447" (approximate; exact depends on Intl impl)
 *
 * Idempotent + fail-soft: if the browser lacks the calendar OR the country
 * is Gregorian, returns the standard date string.
 */
(function () {
  "use strict";

  // Country -> Intl calendar identifier. Anything not listed uses Gregorian.
  var CALENDAR_BY_COUNTRY = {
    // GCC + Levant
    "SA": "islamic-umalqura",
    "AE": "islamic-umalqura",
    "OM": "islamic-umalqura",
    "KW": "islamic-umalqura",
    "QA": "islamic-umalqura",
    "BH": "islamic-umalqura",
    "YE": "islamic",
    "JO": "islamic",
    "LB": "islamic",  // mixed; islamic for muslim users
    "SY": "islamic",
    "IQ": "islamic",
    // North Africa
    "EG": "islamic",
    "MA": "islamic",
    "TN": "islamic",
    "DZ": "islamic",
    "LY": "islamic",
    "SD": "islamic",
    "MR": "islamic",
    // Iran / Afghanistan
    "IR": "persian",
    "AF": "persian",
    // Israel
    "IL": "hebrew",
    // East Africa
    "ET": "ethiopic",
    "ER": "ethiopic",
    // East Asia
    "JP": "japanese",
    "CN": "chinese",
    "TW": "chinese",
    "HK": "chinese",
    "MO": "chinese",
  };

  // Locale string to pair with the calendar (so Intl can produce native script).
  var LOCALE_BY_COUNTRY = {
    "SA": "ar-SA", "AE": "ar-AE", "OM": "ar-OM", "KW": "ar-KW",
    "QA": "ar-QA", "BH": "ar-BH", "YE": "ar-YE", "JO": "ar-JO",
    "LB": "ar-LB", "SY": "ar-SY", "IQ": "ar-IQ",
    "EG": "ar-EG", "MA": "ar-MA", "TN": "ar-TN", "DZ": "ar-DZ",
    "LY": "ar-LY", "SD": "ar-SD", "MR": "ar-MR",
    "IR": "fa-IR", "AF": "fa-AF",
    "IL": "he-IL",
    "ET": "am-ET", "ER": "ti-ER",
    "JP": "ja-JP-u-ca-japanese",
    "CN": "zh-CN-u-ca-chinese",
    "TW": "zh-TW-u-ca-chinese",
    "HK": "zh-HK-u-ca-chinese",
    "MO": "zh-MO-u-ca-chinese",
  };

  function calendarFor(cc) {
    var c = (cc || "").toUpperCase();
    return CALENDAR_BY_COUNTRY[c] || "";
  }

  function localeFor(cc) {
    var c = (cc || "").toUpperCase();
    return LOCALE_BY_COUNTRY[c] || "en";
  }

  function format(value, countryCode, opts) {
    if (!value) return "";
    var date = value instanceof Date ? value : new Date(value);
    if (isNaN(date.getTime())) return "";
    var cal = calendarFor(countryCode);
    if (!cal) {
      // Country uses Gregorian — defer to caller's standard formatter.
      return "";
    }
    var options = Object.assign(
      { year: "numeric", month: "long", day: "numeric", calendar: cal },
      opts || {}
    );
    try {
      var fmt = new Intl.DateTimeFormat(localeFor(countryCode), options);
      return fmt.format(date);
    } catch (_e) {
      return "";
    }
  }

  function sweep() {
    var country = (window.RMCLocalization && window.RMCLocalization.country) || "";
    if (!country) return;
    var nodes = document.querySelectorAll("[data-rmc-non-gregorian-date]");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (el.dataset.rmcNonGregBound === "1") continue;
      var iso = el.getAttribute("data-rmc-non-gregorian-date");
      if (!iso) continue;
      var rendered = format(iso, country);
      if (rendered) {
        // Show parallel rendering as a sibling/replacement; mark bound.
        el.textContent = rendered;
        el.setAttribute("data-rmc-non-greg-rendered", "1");
      }
      el.dataset.rmcNonGregBound = "1";
    }
  }

  function init() {
    if (window.RMCNonGregorian && window.RMCNonGregorian.__bootstrapped) return;
    window.RMCNonGregorian = {
      __bootstrapped: true,
      format: format,
      calendarFor: calendarFor,
      sweep: sweep,
    };
    sweep();
    // Re-sweep after HTMX swaps (HTMX-tolerant w/o requiring HTMX).
    document.body && document.body.addEventListener("htmx:afterSwap", sweep);
  }

  // Wait for RMCLocalization to resolve country before sweeping.
  if (window.RMCLocalization && window.RMCLocalization.__bootstrapped) {
    init();
  } else {
    document.addEventListener("rmc:localization-ready", init, { once: true });
    // Belt-and-braces: if the event fired before this script loaded, kick off
    // after a frame.
    setTimeout(init, 0);
  }
})();
