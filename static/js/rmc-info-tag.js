/**
 * Exceptional info tags — fixed tip layer (What / Why / Watch outs / chips / surface).
 * Escapes overflow:hidden parents; falls back to Bootstrap popover when needed.
 */
(function () {
  var LAYER_ID = "rmc-info-tip-layer";
  var activeBtn = null;

  function infoApiBase() {
    var el = document.querySelector("script[data-tour-info-api]");
    return (el && el.getAttribute("data-tour-info-api")) || "";
  }

  function ensureLayer() {
    var layer = document.getElementById(LAYER_ID);
    if (layer) return layer;
    layer = document.createElement("div");
    layer.id = LAYER_ID;
    layer.className = "rmc-info-tip-layer";
    layer.setAttribute("role", "dialog");
    layer.setAttribute("aria-hidden", "true");
    layer.hidden = true;
    document.body.appendChild(layer);
    return layer;
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function chipList(raw) {
    if (!raw) return [];
    return String(raw)
      .split("|")
      .map(function (s) {
        return s.trim();
      })
      .filter(Boolean)
      .slice(0, 6);
  }

  function buildTipHtml(btn) {
    var title = btn.getAttribute("data-bs-title") || "";
    var what =
      btn.getAttribute("data-rmc-info-what") ||
      btn.getAttribute("data-bs-content") ||
      "";
    var why = btn.getAttribute("data-rmc-info-why") || "";
    var watch = btn.getAttribute("data-rmc-info-watch") || "";
    var surface = btn.getAttribute("data-rmc-info-surface") || "";
    var chips = chipList(btn.getAttribute("data-rmc-info-chips"));
    var html = '<div class="rmc-info-tip">';
    html += '<div class="rmc-info-tip__head">';
    html += '<strong class="rmc-info-tip__title wrap">' + escapeHtml(title) + "</strong>";
    if (surface) {
      html +=
        '<span class="rmc-info-tip__surface truncate">' +
        escapeHtml(surface) +
        "</span>";
    }
    html += "</div>";
    if (what) {
      html += '<div class="rmc-info-tip__block">';
      html += '<span class="rmc-info-tip__kicker">What</span>';
      html += '<p class="rmc-info-tip__text wrap">' + escapeHtml(what) + "</p>";
      html += "</div>";
    }
    if (why) {
      html += '<div class="rmc-info-tip__block">';
      html += '<span class="rmc-info-tip__kicker">Why</span>';
      html += '<p class="rmc-info-tip__text wrap">' + escapeHtml(why) + "</p>";
      html += "</div>";
    }
    if (watch) {
      html += '<div class="rmc-info-tip__block rmc-info-tip__block--watch">';
      html += '<span class="rmc-info-tip__kicker">Watch outs</span>';
      html += '<p class="rmc-info-tip__text wrap">' + escapeHtml(watch) + "</p>";
      html += "</div>";
    }
    if (chips.length) {
      html += '<div class="rmc-info-tip__chips">';
      chips.forEach(function (c) {
        html +=
          '<span class="rmc-info-tip__chip truncate">' + escapeHtml(c) + "</span>";
      });
      html += "</div>";
    }
    html += "</div>";
    return html;
  }

  function positionLayer(layer, btn) {
    var rect = btn.getBoundingClientRect();
    var tip = layer.firstElementChild;
    var tipW = tip ? tip.offsetWidth : 320;
    var tipH = tip ? tip.offsetHeight : 160;
    var gap = 10;
    var left = rect.left + rect.width / 2 - tipW / 2;
    var top = rect.bottom + gap;
    if (left < 8) left = 8;
    if (left + tipW > window.innerWidth - 8) left = window.innerWidth - tipW - 8;
    if (top + tipH > window.innerHeight - 8) {
      top = Math.max(8, rect.top - tipH - gap);
    }
    layer.style.left = Math.round(left) + "px";
    layer.style.top = Math.round(top) + "px";
  }

  function hideTip() {
    var layer = document.getElementById(LAYER_ID);
    if (layer) {
      layer.hidden = true;
      layer.setAttribute("aria-hidden", "true");
      layer.innerHTML = "";
    }
    if (activeBtn) {
      activeBtn.setAttribute("aria-expanded", "false");
      activeBtn = null;
    }
  }

  function showTip(btn) {
    var layer = ensureLayer();
    layer.innerHTML = buildTipHtml(btn);
    layer.hidden = false;
    layer.setAttribute("aria-hidden", "false");
    activeBtn = btn;
    btn.setAttribute("aria-expanded", "true");
    positionLayer(layer, btn);
  }

  function hydrateFromApi(btn) {
    var entity = btn.getAttribute("data-rmc-info-entity");
    var field = btn.getAttribute("data-rmc-info-field");
    var feature = btn.getAttribute("data-rmc-info-feature");
    if (!entity && !field && !feature) return;
    var base = infoApiBase();
    if (!base) return;
    var qs = new URLSearchParams();
    if (entity) qs.set("entity", entity);
    if (field) qs.set("field", field);
    if (feature) qs.set("feature", feature);
    fetch(base + "?" + qs.toString(), { credentials: "same-origin" })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (data) {
        if (!data || !data.ok) return;
        if (data.title) btn.setAttribute("data-bs-title", data.title);
        if (data.body) {
          btn.setAttribute("data-bs-content", data.body);
          if (!btn.getAttribute("data-rmc-info-what")) {
            btn.setAttribute("data-rmc-info-what", data.body);
          }
        }
        if (data.why) btn.setAttribute("data-rmc-info-why", data.why);
        if (data.watch_outs) btn.setAttribute("data-rmc-info-watch", data.watch_outs);
        if (data.chips) {
          btn.setAttribute(
            "data-rmc-info-chips",
            Array.isArray(data.chips) ? data.chips.join("|") : String(data.chips)
          );
        }
        if (data.surface) btn.setAttribute("data-rmc-info-surface", data.surface);
      })
      .catch(function () {});
  }

  function wireBtn(btn) {
    if (btn.getAttribute("data-rmc-info-wired") === "1") return;
    btn.setAttribute("data-rmc-info-wired", "1");
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (activeBtn === btn) {
        hideTip();
        return;
      }
      showTip(btn);
    });
    btn.addEventListener("keydown", function (e) {
      if (e.key === "Escape") hideTip();
    });
    if (
      btn.hasAttribute("data-rmc-info-entity") ||
      btn.hasAttribute("data-rmc-info-feature")
    ) {
      hydrateFromApi(btn);
    }
  }

  function init() {
    document.querySelectorAll(".rmc-info-tag [data-rmc-info-tip], .rmc-info-tag [data-bs-toggle='popover']").forEach(wireBtn);
  }

  document.addEventListener("click", function (e) {
    if (!activeBtn) return;
    var layer = document.getElementById(LAYER_ID);
    if (e.target.closest && (e.target.closest(".rmc-info-tag") || (layer && layer.contains(e.target)))) {
      return;
    }
    hideTip();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") hideTip();
  });
  window.addEventListener(
    "scroll",
    function () {
      if (activeBtn) positionLayer(ensureLayer(), activeBtn);
    },
    true
  );
  window.addEventListener("resize", function () {
    if (activeBtn) positionLayer(ensureLayer(), activeBtn);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  document.addEventListener("rmc-info-tag-auto-ready", init);
})();
