/**
 * rmc-localization-bootstrap.js
 *
 * v3.62.5 (2026-05-22) — Wave 2 local-first.
 *
 * Reads the body data attrs emitted by the localization context processor
 * and exposes a small global so any JS (date pickers, calendar widgets,
 * money formatters, chart axis renderers, etc.) can ask:
 *
 *     RMCLocalization.country        -> "NG"
 *     RMCLocalization.weekStart      -> 1   (0..6, ISO; 0=Sun, 1=Mon, 6=Sat)
 *     RMCLocalization.dateFormat     -> "%d/%m/%Y" (strftime pattern)
 *     RMCLocalization.currency       -> "NGN"
 *     RMCLocalization.isRTL          -> false
 *     RMCLocalization.formatDate(d)  -> "22/05/2026"
 *     RMCLocalization.formatMoney(n) -> "₦1,234.56"
 *
 * Defensive: if the body attrs are absent (legacy template render,
 * pre-context-processor pages, etc.), defaults to Monday-week / DD/MM/YYYY /
 * USD / LTR. Idempotent; safe to load multiple times.
 */
(function () {
  "use strict";

  if (window.RMCLocalization && window.RMCLocalization.__bootstrapped) {
    return;
  }

  var body = document.body || document.documentElement;

  function attr(name, fallback) {
    if (!body) return fallback;
    var v = body.getAttribute(name);
    return v === null || v === "" ? fallback : v;
  }

  var country = attr("data-rmc-country", "");
  var weekStart = parseInt(attr("data-rmc-week-start", "1"), 10);
  if (isNaN(weekStart) || weekStart < 0 || weekStart > 6) weekStart = 1;
  var dateFormat = attr("data-rmc-date-format", "%d/%m/%Y");
  var currency = attr("data-rmc-currency", "USD");
  var isRTL = attr("data-rmc-is-rtl", "0") === "1";

  // Currency symbol table — kept in sync with templatetags/localization.py
  // _CURRENCY_SYMBOLS. Anything not listed falls back to the ISO code.
  var SYMBOLS = {
    USD: "$", EUR: "€", GBP: "£", JPY: "¥", CNY: "¥",
    INR: "₹", NGN: "₦", KES: "KSh", GHS: "GH₵", ZAR: "R",
    EGP: "E£", MAD: "DH", AED: "AED", SAR: "SAR", ILS: "₪",
    TRY: "₺", BRL: "R$", MXN: "$", ARS: "$", COP: "$", CLP: "$",
    PEN: "S/", RUB: "₽", PLN: "zł", SEK: "kr", NOK: "kr",
    DKK: "kr", CHF: "CHF", CAD: "$", AUD: "$", NZD: "$", SGD: "$",
    HKD: "$", KRW: "₩", THB: "฿", IDR: "Rp", MYR: "RM",
    PHP: "₱", VND: "₫", PKR: "₨", BDT: "৳",
    LKR: "Rs", NPR: "Rs",
  };

  // Zero-decimal currencies for display formatting (storage keeps Decimal).
  var ZERO_DECIMAL = { JPY: 1, KRW: 1, VND: 1, IDR: 1, CLP: 1 };

  function pad2(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function formatDate(d) {
    if (!d) return "";
    var date = d instanceof Date ? d : new Date(d);
    if (isNaN(date.getTime())) return "";
    var m = pad2(date.getMonth() + 1);
    var day = pad2(date.getDate());
    var y = date.getFullYear();
    // Replace strftime tokens. Order matters: %Y before %y.
    return dateFormat
      .replace(/%Y/g, y)
      .replace(/%y/g, String(y).slice(-2))
      .replace(/%m/g, m)
      .replace(/%d/g, day);
  }

  function formatMoney(amount, currencyOverride) {
    if (amount === null || amount === undefined || amount === "") return "";
    var num = typeof amount === "number" ? amount : parseFloat(amount);
    if (isNaN(num)) return "";
    var code = (currencyOverride || currency).toUpperCase();
    var symbol = SYMBOLS[code] || code + " ";
    var fixed = ZERO_DECIMAL[code] ? num.toFixed(0) : num.toFixed(2);
    // Insert thousand separators (Intl-free for SSR consistency).
    var parts = fixed.split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return symbol + parts.join(".");
  }

  window.RMCLocalization = {
    __bootstrapped: true,
    country: country,
    weekStart: weekStart,
    dateFormat: dateFormat,
    currency: currency,
    isRTL: isRTL,
    formatDate: formatDate,
    formatMoney: formatMoney,
    // Returns the localized name of weekday `n` (0=Sunday) using browser locale
    // — fine for visual labels in week pickers.
    weekdayName: function (n, short) {
      try {
        var d = new Date(2024, 0, 7 + (n % 7)); // 2024-01-07 was a Sunday
        return d.toLocaleDateString(undefined, {
          weekday: short ? "short" : "long",
        });
      } catch (_e) {
        return ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][n] || "";
      }
    },
  };

  // Emit a custom event so widgets can hook into init after this lands.
  try {
    document.dispatchEvent(new CustomEvent("rmc:localization-ready", {
      detail: window.RMCLocalization,
    }));
  } catch (_e) { /* IE compat irrelevant */ }
})();
