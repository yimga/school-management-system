/* rmc-data-viz.js
 *
 * v3.59.x Wave 11 Agent V (2026-05-22) — data-viz primitives runtime.
 *
 * CSP-safe IIFE (no eval, no inline-event registration, all event wiring
 * via addEventListener). Idempotent via dataset flags so repeated includes
 * (HTMX swap-ins, Turbo partial replaces) never re-bind.
 *
 * Public helpers attached to window.rmcDataViz:
 *   - renderSparklinePath(points, width=120, height=32)
 *       Returns { path: string, fill: string, lastPoint: {cx,cy} }
 *       for the polyline + gradient fill polygon + last-point marker.
 *   - mountSparklines(root?)
 *       Finds [data-rmc-sparkline-points] elements and renders inline SVG.
 *   - mountHeatmapTooltips(root?)
 *       Adds focus-keyboard parity to CSS-driven hover tooltips on
 *       [data-rmc-heatmap-tooltip] / [data-rmc-tooltip-text] tiles.
 *   - mountChartPaletteBridge()
 *       Reads chart-series CSS custom properties off the document root
 *       and exposes them as window.rmcChartPalette for chart libs.
 */
(function () {
  "use strict";

  var W = window;
  if (!W || !W.document) { return; }
  var doc = W.document;

  // ------------------------------------------------------------
  // Internal: parse "10,12,15,14" data attribute into number[]
  // ------------------------------------------------------------
  function parsePoints(raw) {
    if (!raw || typeof raw !== "string") { return []; }
    var out = [];
    var parts = raw.split(/[,\s]+/);
    for (var i = 0; i < parts.length; i++) {
      var t = parts[i].trim();
      if (!t) { continue; }
      var n = parseFloat(t);
      if (isFinite(n)) { out.push(n); }
    }
    return out;
  }

  // ------------------------------------------------------------
  // Public: renderSparklinePath
  // ------------------------------------------------------------
  function renderSparklinePath(points, width, height) {
    width  = (typeof width  === "number" && width  > 0) ? width  : 120;
    height = (typeof height === "number" && height > 0) ? height : 32;
    if (!Array.isArray(points) || points.length === 0) {
      return { path: "", fill: "", lastPoint: null };
    }
    if (points.length === 1) {
      var cy1 = height / 2;
      return {
        path: "M0," + cy1 + " L" + width + "," + cy1,
        fill: "M0," + height + " L0," + cy1 + " L" + width + "," + cy1 + " L" + width + "," + height + " Z",
        lastPoint: { cx: width, cy: cy1 }
      };
    }
    // Normalize Y: invert so larger value = higher on screen.
    var min = points[0], max = points[0];
    for (var i = 1; i < points.length; i++) {
      if (points[i] < min) { min = points[i]; }
      if (points[i] > max) { max = points[i]; }
    }
    var span = max - min;
    var padY = 2;
    var usableH = Math.max(1, height - padY * 2);
    var stepX = (points.length === 1) ? width : (width / (points.length - 1));

    var d = "";
    var lastCX = 0;
    var lastCY = 0;
    for (var j = 0; j < points.length; j++) {
      var cx = j * stepX;
      var ratio = (span === 0) ? 0.5 : ((points[j] - min) / span);
      var cy = padY + (1 - ratio) * usableH;
      d += (j === 0 ? "M" : " L") + cx.toFixed(2) + "," + cy.toFixed(2);
      lastCX = cx;
      lastCY = cy;
    }
    var fill = d + " L" + width.toFixed(2) + "," + height + " L0," + height + " Z";
    return { path: d, fill: fill, lastPoint: { cx: lastCX, cy: lastCY } };
  }

  // ------------------------------------------------------------
  // Public: mountSparklines
  // ------------------------------------------------------------
  var SVG_NS = "http://www.w3.org/2000/svg";

  function mountSparklines(root) {
    var scope = root || doc;
    var nodes;
    try {
      nodes = scope.querySelectorAll("[data-rmc-sparkline-points]");
    } catch (_e) { return 0; }
    var count = 0;
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (el.dataset && el.dataset.rmcSparklineInited === "1") { continue; }
      var raw = el.getAttribute("data-rmc-sparkline-points");
      var pts = parsePoints(raw);
      if (pts.length === 0) {
        if (el.dataset) { el.dataset.rmcSparklineInited = "1"; }
        continue;
      }
      // Read width/height from existing <svg viewBox> if present, else default.
      var width = 120, height = 32;
      var existingSvg = el.querySelector("svg.rmc-sparkline__svg");
      if (existingSvg) {
        var vb = existingSvg.getAttribute("viewBox");
        if (vb) {
          var vbParts = vb.split(/\s+/);
          if (vbParts.length === 4) {
            var w = parseFloat(vbParts[2]); if (isFinite(w) && w > 0) { width = w; }
            var h = parseFloat(vbParts[3]); if (isFinite(h) && h > 0) { height = h; }
          }
        }
      }
      var result = renderSparklinePath(pts, width, height);

      // Build SVG content. Reuse existing svg if present, else create a new one.
      var svg = existingSvg;
      if (!svg) {
        svg = doc.createElementNS(SVG_NS, "svg");
        svg.setAttribute("class", "rmc-sparkline__svg");
        svg.setAttribute("viewBox", "0 0 " + width + " " + height);
        svg.setAttribute("preserveAspectRatio", "none");
        svg.setAttribute("aria-hidden", "true");
        el.appendChild(svg);
      } else {
        // Clear previously-rendered children so this is repeat-safe.
        while (svg.firstChild) { svg.removeChild(svg.firstChild); }
      }

      if (result.fill) {
        var fillEl = doc.createElementNS(SVG_NS, "path");
        fillEl.setAttribute("class", "rmc-sparkline__fill");
        fillEl.setAttribute("d", result.fill);
        svg.appendChild(fillEl);
      }
      if (result.path) {
        var pathEl = doc.createElementNS(SVG_NS, "path");
        pathEl.setAttribute("class", "rmc-sparkline__path");
        pathEl.setAttribute("d", result.path);
        svg.appendChild(pathEl);
      }
      if (result.lastPoint) {
        var dot = doc.createElementNS(SVG_NS, "circle");
        dot.setAttribute("class", "rmc-sparkline__point--last");
        dot.setAttribute("cx", String(result.lastPoint.cx));
        dot.setAttribute("cy", String(result.lastPoint.cy));
        dot.setAttribute("r", "2.4");
        svg.appendChild(dot);
      }
      if (el.dataset) { el.dataset.rmcSparklineInited = "1"; }
      count++;
    }
    return count;
  }

  // ------------------------------------------------------------
  // Public: mountHeatmapTooltips
  // ------------------------------------------------------------
  function mountHeatmapTooltips(root) {
    var scope = root || doc;
    var nodes;
    try {
      nodes = scope.querySelectorAll("[data-rmc-heatmap-tooltip], [data-rmc-tooltip-text]");
    } catch (_e) { return 0; }
    var count = 0;
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (el.dataset && el.dataset.rmcHeatmapTooltipInited === "1") { continue; }
      // Mirror data-rmc-heatmap-tooltip -> data-rmc-tooltip-text so the CSS
      // ::after rule sees it.
      var legacyAttr = el.getAttribute("data-rmc-heatmap-tooltip");
      if (legacyAttr && !el.getAttribute("data-rmc-tooltip-text")) {
        el.setAttribute("data-rmc-tooltip-text", legacyAttr);
      }
      // Make tiles keyboard-focusable if they aren't already.
      if (!el.hasAttribute("tabindex") && el.tagName !== "BUTTON" && el.tagName !== "A") {
        el.setAttribute("tabindex", "0");
      }
      // ARIA label fallback for screen readers.
      if (!el.getAttribute("aria-label")) {
        var lbl = el.getAttribute("data-rmc-tooltip-text") || el.getAttribute("data-label");
        if (lbl) { el.setAttribute("aria-label", lbl); }
      }
      if (el.dataset) { el.dataset.rmcHeatmapTooltipInited = "1"; }
      count++;
    }
    return count;
  }

  // ------------------------------------------------------------
  // Public: mountChartPaletteBridge
  // ------------------------------------------------------------
  function mountChartPaletteBridge() {
    if (!W.getComputedStyle) { return null; }
    var root = doc.documentElement;
    var anchor = doc.querySelector("[data-rmc-chart-palette]") || root;
    var cs;
    try { cs = W.getComputedStyle(anchor); } catch (_e) { return null; }
    var palette = {};
    var families = [
      "--rmc-chart-color-",
      "--chart-series-"
    ];
    for (var f = 0; f < families.length; f++) {
      var prefix = families[f];
      for (var n = 1; n <= 8; n++) {
        var v = cs.getPropertyValue(prefix + n);
        if (v) { v = v.trim(); }
        if (v) {
          palette["color" + n] = v;
          // Last-wins is fine — chart series tokens are the canonical source,
          // but we also expose the namespaced primitives if present.
        }
      }
    }
    W.rmcChartPalette = palette;
    return palette;
  }

  // ------------------------------------------------------------
  // Bootstrap on DOMContentLoaded, then again on htmx:afterSwap.
  // ------------------------------------------------------------
  function boot() {
    if (doc.documentElement.dataset.rmcDataVizBooted === "1") {
      // Re-mount only — covers HTMX partial swap-ins.
      mountSparklines(doc);
      mountHeatmapTooltips(doc);
      return;
    }
    mountSparklines(doc);
    mountHeatmapTooltips(doc);
    mountChartPaletteBridge();
    doc.documentElement.dataset.rmcDataVizBooted = "1";
  }

  if (doc.readyState === "loading") {
    doc.addEventListener("DOMContentLoaded", boot, { once: false });
  } else {
    boot();
  }
  // HTMX partial swap-ins.
  doc.addEventListener("htmx:afterSwap", function (ev) {
    var target = (ev && ev.target) ? ev.target : doc;
    mountSparklines(target);
    mountHeatmapTooltips(target);
  });

  // Expose API.
  W.rmcDataViz = {
    renderSparklinePath: renderSparklinePath,
    mountSparklines: mountSparklines,
    mountHeatmapTooltips: mountHeatmapTooltips,
    mountChartPaletteBridge: mountChartPaletteBridge
  };
})();
