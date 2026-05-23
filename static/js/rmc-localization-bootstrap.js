/**
 * rmc-localization-bootstrap.js
 *
 * v3.62.8 (2026-05-22) — Waves 2 + 6 + 7 local-first.
 *
 * Reads the body data attrs emitted by the localization context processor
 * and exposes a small global so any JS (date pickers, calendar widgets,
 * money formatters, chart axis renderers, etc.) can ask:
 *
 *     RMCLocalization.country         -> "NG"
 *     RMCLocalization.language        -> "fr"  // Wave 6
 *     RMCLocalization.weekStart       -> 1   (0..6, ISO; 0=Sun, 1=Mon, 6=Sat)
 *     RMCLocalization.dateFormat      -> "%d/%m/%Y" (strftime pattern)
 *     RMCLocalization.currency        -> "NGN"
 *     RMCLocalization.isRTL           -> false
 *     RMCLocalization.formatDate(d)   -> "22/05/2026"
 *     RMCLocalization.formatMoney(n)  -> "₦1,234.56"
 *     RMCLocalization.formatNumber(n) -> "1,23,456"  // Wave 7 (Indian)
 *
 * Wave 7 — number grouping: respects the country's locale convention.
 *   - Indian numbering (IN/PK/BD/NP/LK): 1,23,456 (lakh-crore)
 *   - Western (US/EU/most): 1,234,567 (every 3 digits)
 *   - Chinese (CN/JP/KR/TW/HK): 12,3456 (myriad)  -- optional, opt-in via
 *     data-rmc-number-grouping="myriad" because most CJK schools use Western
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
  var language = attr("data-rmc-language", "");  // Wave 6
  var weekStart = parseInt(attr("data-rmc-week-start", "1"), 10);
  if (isNaN(weekStart) || weekStart < 0 || weekStart > 6) weekStart = 1;
  var dateFormat = attr("data-rmc-date-format", "%d/%m/%Y");
  var currency = attr("data-rmc-currency", "USD");
  var isRTL = attr("data-rmc-is-rtl", "0") === "1";

  // Wave 7: countries that use Indian (lakh-crore) digit grouping.
  // Indian numbering writes 1,00,000 (one lakh) not 100,000, then 1,00,00,000
  // (one crore) not 10,000,000. Used across South Asia school reports +
  // fee invoices + admin tables. Convention not the only valid one — operators
  // can override per-tenant later via cockpit_payload.number_grouping.
  var INDIAN_GROUPING = {
    IN:1, PK:1, BD:1, NP:1, LK:1, BT:1, MV:1,
  };

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

  // Wave 7: Indian (lakh-crore) digit grouping. Input is digits-only;
  // output writes the LAST 3 digits, then groups of 2 going leftward.
  // 1234567 -> "12,34,567"  (12 lakh 34 thousand 567)
  // 12345678 -> "1,23,45,678" (1 crore 23 lakh ...)
  function groupIndian(digits) {
    if (digits.length <= 3) return digits;
    var last3 = digits.slice(-3);
    var rest = digits.slice(0, -3);
    rest = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",");
    return rest + "," + last3;
  }

  function groupWestern(digits) {
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  function pickGrouping(cc) {
    return INDIAN_GROUPING[(cc || "").toUpperCase()] ? "indian" : "western";
  }

  function formatNumber(value, opts) {
    if (value === null || value === undefined || value === "") return "";
    var num = typeof value === "number" ? value : parseFloat(value);
    if (isNaN(num)) return "";
    opts = opts || {};
    var maxFrac = opts.maximumFractionDigits != null ? opts.maximumFractionDigits : 2;
    var fixed = num.toFixed(maxFrac);
    var parts = fixed.split(".");
    var groupingMode = opts.grouping || pickGrouping(country);
    parts[0] = (groupingMode === "indian") ? groupIndian(parts[0]) : groupWestern(parts[0]);
    return parts.join(".");
  }

  function formatMoney(amount, currencyOverride) {
    if (amount === null || amount === undefined || amount === "") return "";
    var num = typeof amount === "number" ? amount : parseFloat(amount);
    if (isNaN(num)) return "";
    var code = (currencyOverride || currency).toUpperCase();
    var symbol = SYMBOLS[code] || code + " ";
    var fixed = ZERO_DECIMAL[code] ? num.toFixed(0) : num.toFixed(2);
    var parts = fixed.split(".");
    var groupingMode = pickGrouping(country);
    parts[0] = (groupingMode === "indian") ? groupIndian(parts[0]) : groupWestern(parts[0]);
    return symbol + parts.join(".");
  }

  window.RMCLocalization = {
    __bootstrapped: true,
    country: country,
    language: language,        // Wave 6
    weekStart: weekStart,
    dateFormat: dateFormat,
    currency: currency,
    isRTL: isRTL,
    formatDate: formatDate,
    formatMoney: formatMoney,
    formatNumber: formatNumber,  // Wave 7
    pickGrouping: pickGrouping,  // Wave 7
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

  // v3.62.7 Wave 4: if the user's country is RTL AND the document's dir
  // is still the server-default 'ltr', flip it. Templates can override by
  // emitting an explicit `dir` attr in {{ rmc_text_direction }} which the
  // server-side processor leaves untouched.
  if (isRTL && document.documentElement.getAttribute("dir") !== "rtl") {
    document.documentElement.setAttribute("dir", "rtl");
    document.documentElement.setAttribute("data-rmc-is-rtl-country", "1");
  }

  // Emit a custom event so widgets can hook into init after this lands.
  try {
    document.dispatchEvent(new CustomEvent("rmc:localization-ready", {
      detail: window.RMCLocalization,
    }));
  } catch (_e) { /* IE compat irrelevant */ }

  // v3.62.7 Wave 4: lazy-load the non-Gregorian display layer ONLY when the
  // user's country uses a non-Gregorian primary calendar. Saves ~3KB on
  // every Gregorian page-load (the vast majority of traffic). The layer
  // converts data-rmc-non-gregorian-date elements to Hijri / Hebrew /
  // Ethiopian / Persian / Chinese / Japanese representations as appropriate.
  var NON_GREG_COUNTRIES = {
    SA:1, AE:1, OM:1, KW:1, QA:1, BH:1, YE:1, JO:1, LB:1, SY:1, IQ:1,
    EG:1, MA:1, TN:1, DZ:1, LY:1, SD:1, MR:1,
    IR:1, AF:1, IL:1, ET:1, ER:1,
    JP:1, CN:1, TW:1, HK:1, MO:1,
  };
  if (country && NON_GREG_COUNTRIES[country.toUpperCase()]) {
    var s = document.createElement("script");
    s.src = (document.currentScript && document.currentScript.src
            ? document.currentScript.src.replace(/rmc-localization-bootstrap\.js.*$/, "rmc-non-gregorian-display.js")
            : "/static/js/rmc-non-gregorian-display.js");
    s.defer = true;
    s.async = true;
    (document.head || document.documentElement).appendChild(s);
  }
})();
