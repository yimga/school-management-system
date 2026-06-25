/**
 * Prism Bridge — void-band pulse animations + fleet snapshot sync for C/D captions.
 */
(function () {
  "use strict";

  if (window.__rmcWorldGlobePrism) return;
  window.__rmcWorldGlobePrism = true;

  var SPOTLIGHT_MS = 3000;
  var REFRESH_TICK_MS = 4000;

  function readBootstrap() {
    var el = document.getElementById("rmc-operator-fleet-bootstrap");
    if (!el || !el.textContent) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (_err) {
      return null;
    }
  }

  function setText(id, value) {
    var node = document.getElementById(id);
    if (node) node.textContent = String(value == null ? "—" : value);
  }

  function applyFleet(bundle) {
    var data = bundle || {};
    var caption = document.getElementById("rmc-world-globe-void-caption-text");
    var chromeCaption = document.getElementById("rmc-world-globe-chrome-caption-text");
    if (data.latest_pulse_text) {
      if (caption) caption.textContent = data.latest_pulse_text;
      if (chromeCaption) chromeCaption.textContent = data.latest_pulse_text;
    }
    var whisper = document.getElementById("rmc-world-globe-whisper-line");
    var chromeWhisper = document.getElementById("rmc-world-globe-chrome-whisper-text");
    if (data.whisper_line) {
      if (whisper) whisper.textContent = data.whisper_line;
      if (chromeWhisper) chromeWhisper.textContent = data.whisper_line;
    }
  }

  function sparkColorForCell(cell) {
    if (cell.classList.contains("lx-world__holo-cell--ok")) return "#6ee7b7";
    if (cell.classList.contains("lx-world__holo-cell--warn")) return "#f59e0b";
    return "#64748b";
  }

  function buildSparkSvg(cell) {
    var csv = cell.getAttribute("data-rmc-holo-spark");
    var svg = cell.querySelector("[data-rmc-holo-spark-svg]");
    if (!csv || !svg) return;
    var parts = csv.split(",").map(function (p) {
      return parseFloat(String(p).trim());
    }).filter(function (n) {
      return !isNaN(n);
    });
    if (parts.length < 2) return;
    var min = Math.min.apply(null, parts);
    var max = Math.max.apply(null, parts);
    var range = max - min || 1;
    var w = 36;
    var h = 12;
    var step = w / (parts.length - 1);
    var pts = [];
    var fillPts = ["0," + h];
    for (var i = 0; i < parts.length; i++) {
      var x = i * step;
      var y = h - 2 - ((parts[i] - min) / range) * (h - 4);
      pts.push(x.toFixed(1) + "," + y.toFixed(1));
      fillPts.push(x.toFixed(1) + "," + y.toFixed(1));
    }
    fillPts.push(w + "," + h);
    var color = sparkColorForCell(cell);
    svg.innerHTML =
      '<polygon class="lx-world__holo-spark-fill" fill="' +
      color +
      '" points="' +
      fillPts.join(" ") +
      '"/>' +
      '<polyline fill="none" stroke="' +
      color +
      '" stroke-width="1.4" points="' +
      pts.join(" ") +
      '"/>';
  }

  function countUpValue(el) {
    var raw = el.getAttribute("data-rmc-holo-target");
    if (raw == null || raw === "") return;
    var existing = (el.textContent || "").trim();
    if (/[a-zA-Z]/.test(existing.replace(/^\$/, ""))) return;
    var target = parseInt(raw, 10);
    if (isNaN(target)) return;
    var prefix = "";
    if (existing.charAt(0) === "$") prefix = "$";
    if (target === 0) {
      el.textContent = prefix + "0";
      return;
    }
    var start = performance.now();
    function tick(now) {
      var t = Math.min(1, (now - start) / 700);
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = prefix + Math.round(target * eased);
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function initPrism() {
    var strip = document.getElementById("rmc-globe-prism-holo-strip");
    if (!strip) return;

    var cells = Array.prototype.slice.call(strip.querySelectorAll(".lx-world__holo-cell"));
    cells.forEach(function (cell) {
      buildSparkSvg(cell);
      var valueEl = cell.querySelector(".lx-world__holo-cell-v");
      if (valueEl) countUpValue(valueEl);
    });

    var focusIdx = 0;
    setInterval(function () {
      if (!strip.isConnected) return;
      cells.forEach(function (c) {
        c.classList.remove("lx-world__holo-cell--focus");
      });
      focusIdx = (focusIdx + 1) % cells.length;
      if (cells[focusIdx]) cells[focusIdx].classList.add("lx-world__holo-cell--focus");
    }, SPOTLIGHT_MS);

    var refreshed = document.getElementById("rmc-globe-prism-refreshed");
    function tickRefresh() {
      if (!refreshed) return;
      try {
        refreshed.textContent = new Date().toLocaleTimeString();
      } catch (_e) {
        refreshed.textContent = "just now";
      }
    }
    tickRefresh();
    setInterval(tickRefresh, REFRESH_TICK_MS);
  }

  document.addEventListener("rmc:fleet-snapshot", function (ev) {
    applyFleet(ev.detail || {});
  });
  document.addEventListener("rmc:globe-live-updated", function (ev) {
    var detail = ev.detail || {};
    applyFleet(detail.bundle || detail);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      applyFleet(readBootstrap() || {});
      initPrism();
    });
  } else {
    applyFleet(readBootstrap() || {});
    initPrism();
  }
})();
