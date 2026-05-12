/**
 * Sticky metric ticker — Apple Stocks-style pinned KPI strip.
 *
 * Markup contract (from templates/components/rmc_metric_ticker.html):
 *   <section class="rmc-metric-ticker" data-rmc-metric-ticker>
 *     <div class="rmc-metric-ticker__sentinel"></div>
 *     <div class="rmc-metric-ticker__full row g-3">
 *       <div ...><div class="kpi"> <span class="label">Students</span>
 *                                  <div class="value" data-rmc-metric-value>1,284</div>
 *                                  <div data-rmc-metric-delta>+12</div> </div></div>
 *       ...
 *     </div>
 *     <div class="rmc-metric-ticker__pin" data-rmc-metric-pin hidden></div>
 *   </section>
 *
 * Behavior:
 *   1. On mount, project the full cards into the pin container as compact rows.
 *   2. IntersectionObserver watches the sentinel — when it leaves the viewport,
 *      set [data-pinned="1"] on the host; the CSS reveals the pin.
 *   3. MutationObserver tracks live updates inside .__full so the pin mirror
 *      stays in sync without re-mounting.
 *
 * Mounted globally via portal_base / control_plane_skeleton / admin base_site
 * so any page that includes the partial gets the behavior for free.
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  function projectFullToPin(host) {
    var pin = host.querySelector("[data-rmc-metric-pin]");
    if (!pin) return;
    var cards = host.querySelectorAll(".rmc-metric-ticker__full .kpi");
    var frag = document.createDocumentFragment();
    for (var i = 0; i < cards.length; i++) {
      var card = cards[i];
      var label = card.querySelector(".label");
      var value = card.querySelector("[data-rmc-metric-value], .value");
      var delta = card.querySelector("[data-rmc-metric-delta]");
      if (!label || !value) continue;
      var item = document.createElement("span");
      item.className = "rmc-metric-ticker__pin-item";
      var lbl = document.createElement("span");
      lbl.className = "rmc-metric-ticker__pin-item-label";
      lbl.textContent = label.textContent.trim();
      var val = document.createElement("span");
      val.className = "rmc-metric-ticker__pin-item-value";
      val.textContent = value.textContent.trim();
      item.appendChild(lbl);
      item.appendChild(val);
      if (delta) {
        var d = document.createElement("span");
        var tone = "neutral";
        var dClasses = (delta.className || "").split(" ");
        for (var k = 0; k < dClasses.length; k++) {
          var m = /rmc-metric-ticker__delta--(success|warning|danger|neutral)/.exec(dClasses[k]);
          if (m) { tone = m[1]; break; }
        }
        d.className = "rmc-metric-ticker__pin-item-delta rmc-metric-ticker__pin-item-delta--" + tone;
        d.textContent = delta.textContent.trim();
        item.appendChild(d);
      }
      frag.appendChild(item);
    }
    pin.textContent = "";
    pin.appendChild(frag);
    pin.removeAttribute("hidden");
  }

  function mount(host) {
    if (host.__rmcMetricTickerMounted) return;
    host.__rmcMetricTickerMounted = true;
    projectFullToPin(host);

    var sentinel = host.querySelector(".rmc-metric-ticker__sentinel");
    if (!sentinel || typeof IntersectionObserver !== "function") {
      /* No IO support — degrade to always-pinned-when-scrolled fallback. */
      function fallback() {
        var rect = host.getBoundingClientRect();
        host.setAttribute("data-pinned", rect.bottom < 80 ? "1" : "0");
      }
      window.addEventListener("scroll", fallback, { passive: true });
      fallback();
      return;
    }

    var io = new IntersectionObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        var e = entries[i];
        if (e.target === sentinel) {
          /* Sentinel intersecting means we're still at the top — unpin. */
          host.setAttribute("data-pinned", e.isIntersecting ? "0" : "1");
        }
      }
    }, { rootMargin: "0px 0px 0px 0px", threshold: 0 });
    io.observe(sentinel);

    /* Live data updates inside the full block — re-project. Debounced via rAF. */
    var rafToken = 0;
    var mo = new MutationObserver(function () {
      if (rafToken) return;
      rafToken = requestAnimationFrame(function () {
        rafToken = 0;
        projectFullToPin(host);
      });
    });
    var full = host.querySelector(".rmc-metric-ticker__full");
    if (full) {
      mo.observe(full, { childList: true, subtree: true, characterData: true });
    }
  }

  function mountAll() {
    var hosts = document.querySelectorAll("[data-rmc-metric-ticker]");
    for (var i = 0; i < hosts.length; i++) mount(hosts[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAll);
  } else {
    mountAll();
  }

  /* Re-mount after HTMX swaps (used by some dashboards for live KPI refresh). */
  document.body && document.body.addEventListener("htmx:afterSwap", mountAll);
})();
