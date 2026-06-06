/**
 * Sovereign kernel sandbox wizard (2026-06-05 rebuild).
 *
 * The deployment matrix is computed 100% CLIENT-SIDE and ALWAYS renders, so the
 * sim can never show "could not reach validation service". The backend
 * /marketing/api/sandbox-validate/ is still pinged as a NON-BLOCKING progressive
 * enhancement (funnel analytics + server-side step mapping) — but a failure is
 * silent and never affects what the visitor sees.
 */
(function () {
  "use strict";

  // region -> {gov term, currency, symbol, fx rate vs USD, rtl, core label}
  var REGION = {
    US: { gov: "District management", cur: "USD", sym: "$", rate: 1, rtl: false },
    GB: { gov: "Trust / MAT management", cur: "GBP", sym: "£", rate: 0.79, rtl: false },
    NG: { gov: "State ministry integration", cur: "NGN", sym: "₦", rate: 1550, rtl: false },
    KE: { gov: "County education office", cur: "KES", sym: "KSh", rate: 129, rtl: false },
    IN: { gov: "Board affiliation (CBSE/ICSE)", cur: "INR", sym: "₹", rate: 83, rtl: false },
    BR: { gov: "Secretaria de Educação", cur: "BRL", sym: "R$", rate: 5.1, rtl: false },
    SA: { gov: "Ministry of Education integration", cur: "SAR", sym: "ر.س", rate: 3.75, rtl: true },
    AE: { gov: "Ministry / KHDA integration", cur: "AED", sym: "د.إ", rate: 3.67, rtl: true },
    ID: { gov: "Dinas Pendidikan integration", cur: "IDR", sym: "Rp", rate: 16200, rtl: false },
    CA: { gov: "School board management", cur: "CAD", sym: "C$", rate: 1.36, rtl: false }
  };
  var SIZE_WEEKS = { small: 4, medium: 8, large: 12 };
  var SIZE_BASE = { small: 600, medium: 1800, large: 6000 };
  var SIZE_LABEL = { small: "Under 500", medium: "500–2,000", large: "2,000+" };

  function getCookie(name) {
    var m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }
  // Prefer the form's hidden {% csrf_token %} input — the csrftoken cookie is
  // HttpOnly in prod, so document.cookie can't read it.
  function csrfToken(form) {
    var f = form && form.querySelector('input[name="csrfmiddlewaretoken"]');
    return (f && f.value) || getCookie("csrftoken");
  }
  function fmt(n) {
    return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
  }

  function selectedModules(form) {
    var out = [];
    form.querySelectorAll('input[name="modules"]:checked').forEach(function (el) {
      out.push(el.value);
    });
    return out;
  }

  function row(k, v, em) {
    return (
      '<div class="mkt-sov-result__row"><span class="mkt-sov-result__k">' +
      k +
      '</span><span class="mkt-sov-result__v' +
      (em ? " is-em" : "") +
      '">' +
      v +
      "</span></div>"
    );
  }

  function renderMatrix(form) {
    var regionVal = (form.querySelector('[name="region"]') || {}).value || "US";
    var r = REGION[regionVal] || REGION.US;
    var sizeVal = (form.querySelector('[name="school_size"]') || {}).value || "medium";
    var mods = selectedModules(form);
    var price = Math.round(SIZE_BASE[sizeVal] * r.rate * (1 + mods.length * 0.12));

    var result = form.parentNode.querySelector("[data-mkt-sov-result]") ||
      form.querySelector("[data-mkt-sov-result]");
    if (!result) return;

    var html =
      row("Governing body", r.gov) +
      row("Localized currency", r.cur + "  " + r.sym) +
      row("Estimated setup", SIZE_WEEKS[sizeVal] + " weeks", true) +
      row("Indicative monthly", r.sym + " " + fmt(price) + " / mo") +
      row("School size", SIZE_LABEL[sizeVal]) +
      row("Modules enabled", mods.length ? mods.length + " active" : "none");
    if (r.rtl) {
      html +=
        '<p class="mkt-sov-result__rtl">↻ Right-to-left layout + Arabic script rendered natively for this region.</p>';
    }
    result.innerHTML = html;
    result.hidden = false;

    // update the live "core active" badge
    var badge = (form.closest("[data-mkt-sandbox-wizard]") || document).querySelector(
      "[data-mkt-sandbox-badge]"
    );
    if (badge) badge.textContent = regionVal + " Core Active";
  }

  // Non-blocking backend ping — failure is silent, never shown to the visitor.
  function pingBackend(form) {
    var payload = {
      region: (form.querySelector('[name="region"]') || {}).value || "US",
      school_size: (form.querySelector('[name="school_size"]') || {}).value || "medium",
      modules: selectedModules(form)
    };
    try {
      fetch("/marketing/api/sandbox-validate/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(form) },
        credentials: "same-origin",
        body: JSON.stringify(payload)
      }).catch(function () {
        /* silent — the client-side matrix is the source of truth */
      });
    } catch (_e) {
      /* silent */
    }
  }

  function syncRegionFromBody(form) {
    var select = form.querySelector('[name="region"]');
    if (!select) return;
    var cc = (document.body.getAttribute("data-rmc-country") || "").toUpperCase();
    if (cc && select.querySelector('option[value="' + cc + '"]')) select.value = cc;
  }

  function init(form) {
    syncRegionFromBody(form);
    var rendered = false;

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      renderMatrix(form);
      rendered = true;
      pingBackend(form);
    });

    // Live updates once the matrix is showing.
    form.addEventListener("change", function () {
      if (rendered) renderMatrix(form);
    });
  }

  // Stat count-up on reveal.
  function countUp() {
    var nodes = document.querySelectorAll("[data-mkt-count]");
    if (!nodes.length) return;
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return;
          var el = e.target;
          var target = parseInt(el.getAttribute("data-mkt-count"), 10) || 0;
          var n = 0;
          var step = Math.max(1, Math.round(target / 36));
          el.textContent = "0";
          var id = setInterval(function () {
            n += step;
            if (n >= target) {
              n = target;
              clearInterval(id);
            }
            el.textContent = n;
          }, 24);
          io.unobserve(el);
        });
      },
      { threshold: 0.5 }
    );
    nodes.forEach(function (el) {
      io.observe(el);
    });
  }

  document.querySelectorAll("[data-mkt-sandbox-form]").forEach(init);
  countUp();
})();
