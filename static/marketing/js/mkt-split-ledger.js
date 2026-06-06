/**
 * Clinical Ledger split-payment simulator (2026-06-05).
 * Runs 100% client-side — region-aware currency + e-invoice tax authority,
 * live split distribution (80% tuition / 10% transport / 10% uniform), and an
 * animated government e-invoice stamp on "Process payment". No backend call, so
 * it can never show a "could not reach validation service" error.
 */
(function () {
  "use strict";

  // ISO2 -> region commerce profile. fx scales the slider (held in a neutral
  // unit) into a regionally believable magnitude. Illustrative, not a quote.
  var REGION = {
    US: { cur: "USD", sym: "$", fx: 1, taxLabel: "Sales Tax", taxRate: 7.25, auth: "IRS", rails: ["ACH", "Card", "Apple Pay"] },
    GB: { cur: "GBP", sym: "£", fx: 0.8, taxLabel: "VAT", taxRate: 20, auth: "HMRC", rails: ["Bacs", "Card", "Open Banking"] },
    AE: { cur: "AED", sym: "د.إ", fx: 3.67, taxLabel: "VAT", taxRate: 5, auth: "FTA", rails: ["Card", "Apple Pay", "Bank transfer"], rtl: true },
    SA: { cur: "SAR", sym: "ر.س", fx: 3.75, taxLabel: "VAT", taxRate: 15, auth: "ZATCA", rails: ["mada", "Card", "sadad"], rtl: true },
    NG: { cur: "NGN", sym: "₦", fx: 1500, taxLabel: "VAT", taxRate: 7.5, auth: "FIRS", rails: ["Paystack", "Bank transfer", "USSD"] },
    KE: { cur: "KES", sym: "KSh", fx: 130, taxLabel: "VAT", taxRate: 16, auth: "KRA", rails: ["M-Pesa", "Card", "Bank"] },
    IN: { cur: "INR", sym: "₹", fx: 83, taxLabel: "GST", taxRate: 18, auth: "GSTN", rails: ["UPI", "NetBanking", "Card"] },
    BR: { cur: "BRL", sym: "R$", fx: 5, taxLabel: "NF-e", taxRate: 17, auth: "SEFAZ", rails: ["Pix", "Boleto", "Card"] },
    MX: { cur: "MXN", sym: "$", fx: 17, taxLabel: "CFDI", taxRate: 16, auth: "SAT", rails: ["SPEI", "CoDi", "OXXO"] },
    ID: { cur: "IDR", sym: "Rp", fx: 16000, taxLabel: "PPN", taxRate: 11, auth: "DJP", rails: ["QRIS", "Bank transfer", "Card"] }
  };

  var SPLIT = [
    { key: "tuition", label: "Tuition — school", pct: 0.8 },
    { key: "transport", label: "Transport — bus vendor", pct: 0.1 },
    { key: "uniform", label: "Uniform — vendor", pct: 0.1 }
  ];

  var serial = 1000;

  function fmt(region, value) {
    var n = Math.round(value);
    var grouped = String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return region.sym + grouped;
  }

  function regionFor(code) {
    return REGION[(code || "US").toUpperCase()] || REGION.US;
  }

  // Back-compat: the older compact split markup (shared
  // _mkt_split_ledger_compact.html) is just a slider that resizes two SVG bars.
  // Drive it when the rich clinical-ledger hooks are absent so that surface
  // keeps working without the full region-aware console.
  function initCompact(root) {
    var slider = root.querySelector("[data-mkt-split-slider]");
    var svg = root.querySelector(".mkt-viz--split-ledger");
    if (!slider || !svg) return false;
    var tuition = svg.querySelector("rect:nth-of-type(3)");
    var activity = svg.querySelector("rect:nth-of-type(4)");
    if (!tuition || !activity) return false;
    function apply() {
      var pct = Number(slider.value) / 100;
      var totalW = 352;
      var tW = Math.round(totalW * pct);
      tuition.setAttribute("width", String(tW));
      activity.setAttribute("x", String(24 + tW + 12));
      activity.setAttribute("width", String(totalW - tW));
      slider.setAttribute("aria-valuenow", slider.value);
    }
    slider.addEventListener("input", apply);
    apply();
    return true;
  }

  function init(root) {
    var form = root.querySelector("[data-mkt-cl-form]");
    var regionSel = root.querySelector("[data-mkt-cl-region]");
    var slider = root.querySelector("[data-mkt-cl-slider]");
    var amountEl = root.querySelector("[data-mkt-cl-amount]");
    var railsEl = root.querySelector("[data-mkt-cl-rails]");
    var rowsEl = root.querySelector("[data-mkt-cl-rows]");
    var bar = root.querySelector("[data-mkt-cl-bar]");
    var stamp = root.querySelector("[data-mkt-cl-stamp]");
    var stampAuth = root.querySelector("[data-mkt-cl-stamp-auth]");
    var stampId = root.querySelector("[data-mkt-cl-stamp-id]");
    var processBtn = root.querySelector("[data-mkt-cl-process]");
    // Older compact markup → run the legacy slider behaviour and stop.
    if (!regionSel || !slider || !rowsEl || !bar) { initCompact(root); return; }

    // seed region from server geo
    var seed = (root.getAttribute("data-mkt-default-region") || "US").toUpperCase();
    if (REGION[seed]) regionSel.value = seed;

    function currentRegion() {
      return regionFor(regionSel.value);
    }

    function invoiceAmount(region) {
      return Number(slider.value) * region.fx;
    }

    function renderRails(region) {
      if (!railsEl) return;
      railsEl.textContent = "";
      region.rails.forEach(function (r) {
        var li = document.createElement("li");
        li.textContent = r;
        railsEl.appendChild(li);
      });
    }

    function renderRows(region) {
      var invoice = invoiceAmount(region);
      rowsEl.textContent = "";

      SPLIT.forEach(function (s) {
        var tr = document.createElement("tr");

        var tdLabel = document.createElement("td");
        var dot = document.createElement("span");
        dot.className = "mkt-cl-row__dot mkt-cl-row__dot--" + s.key;
        tdLabel.appendChild(dot);
        var lab = document.createElement("span");
        lab.className = "mkt-cl-row__label";
        lab.textContent = s.label;
        tdLabel.appendChild(lab);

        var tdPct = document.createElement("td");
        tdPct.className = "mkt-cl-row__pct";
        tdPct.textContent = Math.round(s.pct * 100) + "%";

        var tdVal = document.createElement("td");
        tdVal.className = "mkt-cl-row__val";
        tdVal.textContent = fmt(region, invoice * s.pct);

        tr.appendChild(tdLabel);
        tr.appendChild(tdPct);
        tr.appendChild(tdVal);
        rowsEl.appendChild(tr);
      });

      // Tax row
      var tax = invoice * (region.taxRate / 100);
      var taxTr = document.createElement("tr");
      taxTr.className = "is-tax";
      var taxLabelTd = document.createElement("td");
      var taxLab = document.createElement("span");
      taxLab.className = "mkt-cl-row__label";
      taxLab.textContent = region.taxLabel + " (" + region.auth + ")";
      taxLabelTd.appendChild(taxLab);
      var taxBadge = document.createElement("span");
      taxBadge.className = "mkt-cl-badge mkt-cl-badge--tax";
      taxBadge.textContent = "E-INVOICE";
      taxLabelTd.appendChild(taxBadge);
      var taxPctTd = document.createElement("td");
      taxPctTd.className = "mkt-cl-row__pct";
      taxPctTd.textContent = region.taxRate + "%";
      var taxValTd = document.createElement("td");
      taxValTd.className = "mkt-cl-row__val";
      taxValTd.textContent = fmt(region, tax);
      taxTr.appendChild(taxLabelTd);
      taxTr.appendChild(taxPctTd);
      taxTr.appendChild(taxValTd);
      rowsEl.appendChild(taxTr);

      // Total row
      var totalTr = document.createElement("tr");
      totalTr.className = "is-total";
      var totLabelTd = document.createElement("td");
      var totLab = document.createElement("span");
      totLab.className = "mkt-cl-row__label";
      totLab.textContent = "Total settled";
      totLabelTd.appendChild(totLab);
      var totBadge = document.createElement("span");
      totBadge.className = "mkt-cl-badge mkt-cl-badge--ok";
      totBadge.textContent = "RECONCILED";
      totLabelTd.appendChild(totBadge);
      var totPctTd = document.createElement("td");
      totPctTd.className = "mkt-cl-row__pct";
      totPctTd.textContent = "100%";
      var totValTd = document.createElement("td");
      totValTd.className = "mkt-cl-row__val";
      totValTd.textContent = fmt(region, invoice + tax);
      totalTr.appendChild(totLabelTd);
      totalTr.appendChild(totPctTd);
      totalTr.appendChild(totValTd);
      rowsEl.appendChild(totalTr);

      if (amountEl) amountEl.textContent = fmt(region, invoice);
    }

    function animateBar() {
      // reflow so the width transition re-triggers
      SPLIT.forEach(function (s) {
        var seg = bar.querySelector('[data-seg="' + s.key + '"]');
        if (seg) seg.style.width = "0";
      });
      // force reflow
      void bar.offsetWidth;
      SPLIT.forEach(function (s) {
        var seg = bar.querySelector('[data-seg="' + s.key + '"]');
        if (seg) seg.style.width = (s.pct * 100) + "%";
      });
    }

    function applyRTL(region) {
      // The clinical section mirrors only when the seeded/selected region is RTL.
      root.setAttribute("dir", region.rtl ? "rtl" : "ltr");
    }

    function refresh(animate) {
      var region = currentRegion();
      renderRails(region);
      renderRows(region);
      applyRTL(region);
      if (animate) animateBar();
    }

    function processPayment() {
      var region = currentRegion();
      animateBar();
      if (stamp && stampAuth && stampId) {
        serial += 1;
        stampAuth.textContent = region.auth + " · " + region.taxLabel;
        stampId.textContent =
          region.cur + "-" + serial + "-" + Math.round(invoiceAmount(region));
        stamp.classList.remove("is-stamped");
        void stamp.offsetWidth;
        stamp.classList.add("is-stamped");
      }
    }

    regionSel.addEventListener("change", function () { refresh(true); });
    slider.addEventListener("input", function () { refresh(false); });
    if (processBtn) processBtn.addEventListener("click", processPayment);
    if (form) form.addEventListener("submit", function (e) { e.preventDefault(); processPayment(); });

    refresh(true);
  }

  document.querySelectorAll("[data-mkt-split-ledger]").forEach(init);
})();
