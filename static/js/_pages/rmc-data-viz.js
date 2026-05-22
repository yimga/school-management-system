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
  //
  // Wave B (2026-05-22): JS-driven positioned tooltip with secondary stat
  // support. Reads data-label / data-cell-value / data-cell-secondary off
  // the tile and renders into a single shared tooltip element appended to
  // <body>. Behavior:
  //   - Shown on mouseenter AND focus-visible
  //   - Positions above the tile by default; flips below if it would clip
  //     at the top of the viewport
  //   - Horizontally clamped within the viewport (8px gutter)
  //   - role="tooltip" + tile gets aria-describedby pointing at it
  //   - Escape key dismisses while a tile is focused
  //   - Honors prefers-reduced-motion (no opacity fade)
  //   - Idempotent — single document-scoped tooltip element + handler
  //     registry guarded via documentElement.dataset.rmcHeatmapTooltipBound
  // ------------------------------------------------------------
  var _heatmapTooltipEl = null;
  var _heatmapTooltipActiveTile = null;

  function _ensureHeatmapTooltipEl() {
    if (_heatmapTooltipEl && _heatmapTooltipEl.isConnected) { return _heatmapTooltipEl; }
    var t = doc.createElement("div");
    t.className = "rmc-heatmap__tooltip";
    t.id = "rmc-heatmap-tooltip-" + Math.floor(Date.now() % 1000000);
    t.setAttribute("role", "tooltip");
    t.setAttribute("aria-hidden", "true");
    t.dataset.rmcHeatmapTooltipState = "hidden";
    // Three child spans — label / primary value / secondary stat.
    var labelEl = doc.createElement("span");
    labelEl.className = "rmc-heatmap__tooltip-label";
    var valueEl = doc.createElement("span");
    valueEl.className = "rmc-heatmap__tooltip-value";
    var secEl = doc.createElement("span");
    secEl.className = "rmc-heatmap__tooltip-secondary";
    t.appendChild(labelEl);
    t.appendChild(valueEl);
    t.appendChild(secEl);
    if (doc.body) { doc.body.appendChild(t); }
    _heatmapTooltipEl = t;
    return t;
  }

  function _showHeatmapTooltip(tile) {
    if (!tile || !tile.getAttribute) { return; }
    var t = _ensureHeatmapTooltipEl();
    if (!t) { return; }
    var label = tile.getAttribute("data-label") || tile.getAttribute("data-rmc-tooltip-text") || "";
    var value = tile.getAttribute("data-cell-value") || "";
    var secondary = tile.getAttribute("data-cell-secondary") || "";
    // Reset content (textContent — no HTML injection).
    var children = t.children;
    if (children.length >= 3) {
      children[0].textContent = label;
      children[1].textContent = value;
      children[1].style.display = value ? "" : "none";
      children[2].textContent = secondary;
      children[2].style.display = secondary ? "" : "none";
    }
    // Anchor relationship for screen readers.
    tile.setAttribute("aria-describedby", t.id);
    _heatmapTooltipActiveTile = tile;
    // Position. Measure tile + tooltip; flip + clamp.
    t.dataset.rmcHeatmapTooltipState = "measuring";
    t.style.visibility = "hidden";
    t.style.display = "block";
    t.classList.remove("rmc-heatmap__tooltip--below");
    var rect = tile.getBoundingClientRect();
    var tipRect = t.getBoundingClientRect();
    var gutter = 8;
    var tipW = tipRect.width;
    var tipH = tipRect.height;
    // Default: above tile, horizontally centered.
    var topY = rect.top - tipH - gutter;
    var flipped = false;
    if (topY < gutter) {
      // Flip below if would clip at top of viewport.
      topY = rect.bottom + gutter;
      flipped = true;
    }
    var centerX = rect.left + (rect.width / 2) - (tipW / 2);
    // Clamp horizontally within viewport.
    var maxX = (W.innerWidth || doc.documentElement.clientWidth) - tipW - gutter;
    if (centerX < gutter) { centerX = gutter; }
    if (centerX > maxX) { centerX = maxX; }
    t.style.left = centerX + "px";
    t.style.top = topY + "px";
    if (flipped) { t.classList.add("rmc-heatmap__tooltip--below"); }
    t.setAttribute("aria-hidden", "false");
    t.dataset.rmcHeatmapTooltipState = "visible";
    t.style.visibility = "";
  }

  function _hideHeatmapTooltip() {
    var t = _heatmapTooltipEl;
    if (_heatmapTooltipActiveTile) {
      try { _heatmapTooltipActiveTile.removeAttribute("aria-describedby"); } catch (_e) { /* noop */ }
    }
    _heatmapTooltipActiveTile = null;
    if (!t) { return; }
    t.setAttribute("aria-hidden", "true");
    t.dataset.rmcHeatmapTooltipState = "hidden";
    t.style.display = "none";
  }

  function _bindHeatmapTooltipGlobalHandlers() {
    if (doc.documentElement.dataset.rmcHeatmapTooltipBound === "1") { return; }
    doc.documentElement.dataset.rmcHeatmapTooltipBound = "1";
    // Delegated mouseenter / focus via mouseover + focusin (capture-phase
    // for focus so we catch focus-visible from keyboard nav).
    doc.addEventListener("mouseover", function (ev) {
      var t = ev.target;
      if (!t || !t.closest) { return; }
      var tile = t.closest("[data-rmc-heatmap-tooltip], [data-rmc-tooltip-text].rmc-heatmap__tile");
      if (!tile) { return; }
      // Only show if tile has data-cell-value or data-cell-secondary OR
      // there's no CSS ::after fallback configured. Always show for
      // keyboard parity below.
      var hasExtras = tile.hasAttribute("data-cell-value") || tile.hasAttribute("data-cell-secondary");
      if (!hasExtras) { return; }
      _showHeatmapTooltip(tile);
    });
    doc.addEventListener("mouseout", function (ev) {
      var t = ev.target;
      if (!t || !t.closest) { return; }
      var tile = t.closest("[data-rmc-heatmap-tooltip], [data-rmc-tooltip-text].rmc-heatmap__tile");
      if (!tile) { return; }
      // Hide unless related target is still inside the same tile.
      var rel = ev.relatedTarget;
      if (rel && tile.contains(rel)) { return; }
      _hideHeatmapTooltip();
    });
    doc.addEventListener("focusin", function (ev) {
      var t = ev.target;
      if (!t || !t.matches) { return; }
      if (t.matches(".rmc-heatmap__tile, [data-rmc-heatmap-tooltip], [data-rmc-tooltip-text]")) {
        _showHeatmapTooltip(t);
      }
    });
    doc.addEventListener("focusout", function (ev) {
      var t = ev.target;
      if (!t || !t.matches) { return; }
      if (t.matches(".rmc-heatmap__tile, [data-rmc-heatmap-tooltip], [data-rmc-tooltip-text]")) {
        _hideHeatmapTooltip();
      }
    });
    // Escape key dismiss while a tile is keyboard-focused.
    doc.addEventListener("keydown", function (ev) {
      if (ev.key !== "Escape" && ev.keyCode !== 27) { return; }
      if (!_heatmapTooltipActiveTile) { return; }
      var blurTarget = _heatmapTooltipActiveTile;
      _hideHeatmapTooltip();
      // Move focus off the tile so the tooltip stays dismissed.
      try { blurTarget.blur(); } catch (_e) { /* noop */ }
    });
    // Hide on scroll / resize so the tooltip doesn't drift away from its
    // anchor tile.
    W.addEventListener("scroll", _hideHeatmapTooltip, true);
    W.addEventListener("resize", _hideHeatmapTooltip);
  }

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
    // Bind global handlers once per document (idempotent).
    _bindHeatmapTooltipGlobalHandlers();
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
