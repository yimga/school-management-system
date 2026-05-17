/**
 * Illustrative pricing currency switcher (Phase 3 pricing v3).
 * Base amounts are indicative only — not commercial quotes.
 *
 * Uses Intl.NumberFormat when available, so number grouping + decimal
 * separators follow the active page language (e.g. 9.000 in de-DE vs 9,000
 * in en-US). The page language is read from <html lang="..">.
 */
(function () {
  var STUBS = {
    starter: { USD: 3, GBP: 2.5, EUR: 2.8, JPY: 450, RUB: 280, TRY: 100, BRL: 16, INR: 250, CNY: 22, XAF: 1800, XOF: 1800, NGN: 4500, KES: 390, ZAR: 55, GHS: 38 },
    growth:  { USD: 6, GBP: 5,   EUR: 5.5, JPY: 900, RUB: 560, TRY: 200, BRL: 32, INR: 500, CNY: 44, XAF: 3600, XOF: 3600, NGN: 9000, KES: 780, ZAR: 110, GHS: 76 },
    enterprise: {},
  };

  // Fallback symbols for currencies that Intl.NumberFormat can't shorten cleanly
  // (West/Central African CFA franc) — used only when style="currency" fails.
  var FALLBACK_SYMBOLS = {
    XAF: "FCFA ",
    XOF: "CFA ",
    GHS: "GH₵",
  };

  function pageLocale() {
    var html = document.documentElement;
    return (html && html.getAttribute("lang")) || "en";
  }

  function customLabel() {
    var loc = pageLocale().toLowerCase();
    if (loc.indexOf("es") === 0) return "Personalizado";
    if (loc.indexOf("pt") === 0) return "Personalizado";
    if (loc.indexOf("fr") === 0) return "Personnalisé";
    if (loc.indexOf("de") === 0) return "Auf Anfrage";
    if (loc.indexOf("it") === 0) return "Personalizzato";
    if (loc.indexOf("ar") === 0) return "خاص";
    if (loc.indexOf("ru") === 0) return "Под запрос";
    if (loc.indexOf("tr") === 0) return "Özel";
    if (loc.indexOf("ja") === 0) return "カスタム";
    if (loc.indexOf("zh") === 0) return "定制";
    if (loc.indexOf("hi") === 0) return "कस्टम";
    return "Custom";
  }

  function formatAmount(code, value) {
    if (value == null) return customLabel();
    var locale = pageLocale();
    if (typeof Intl !== "undefined" && typeof Intl.NumberFormat === "function") {
      try {
        return new Intl.NumberFormat(locale, {
          style: "currency",
          currency: code,
          maximumFractionDigits: value < 10 ? 1 : 0,
        }).format(value);
      } catch (e) {
        // Some locales / currency combos throw; fall through to plain symbol.
      }
    }
    var sym = FALLBACK_SYMBOLS[code] || code + " ";
    return sym + value;
  }

  function applyCurrency(code) {
    document.querySelectorAll("[data-mkt-price-stub] [data-plan]").forEach(function (el) {
      var plan = el.getAttribute("data-plan");
      var table = STUBS[plan] || {};
      var val = table[code];
      el.textContent = formatAmount(code, val);
    });
  }

  function init() {
    var root = document.querySelector("[data-mkt-currency-switcher]");
    if (!root) return;
    var select = root.querySelector("select");
    if (!select) return;
    applyCurrency(select.value || "USD");
    select.addEventListener("change", function () {
      applyCurrency(select.value);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
