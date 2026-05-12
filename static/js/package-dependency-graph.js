/**
 * N17: Interactive dependency graph (pan + zoom) for package upstream/downstream edges.
 * No external deps — SVG + mouse + wheel.
 *
 * Multiple graphs per page: unique SVG marker IDs per render; document-level mouseup removed after drag.
 */
(function (global) {
  "use strict";

  function clamp(n, a, b) {
    return Math.max(a, Math.min(b, n));
  }

  function tok(name, fallback) {
    try {
      var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return v || fallback;
    } catch (_e) { return fallback; }
  }

  function sanitizeId(s) {
    return String(s || "").replace(/[^a-zA-Z0-9_-]/g, "_");
  }

  function uniqueSuffix() {
    return "g" + Math.random().toString(36).slice(2, 11);
  }

  /**
   * @param {HTMLElement} mount - container (receives inner SVG wrap)
   * @param {{ center_id?: string, upstream_package_ids?: string[], downstream_package_ids?: string[] }} graph
   */
  function renderPackageDependencyGraph(mount, graph) {
    if (!mount) return;
    var centerId = (graph && graph.center_id) || "package";
    var up = (graph && graph.upstream_package_ids) || [];
    var down = (graph && graph.downstream_package_ids) || [];

    mount.innerHTML = "";
    var wrap = document.createElement("div");
    wrap.className = "rmc-pkg-graph-inner position-relative";
    wrap.style.cursor = "grab";
    wrap.style.touchAction = "none";

    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", "260");
    svg.setAttribute("viewBox", "0 0 420 260");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Package dependency graph");

    var markerId = "rmc-arrow-" + uniqueSuffix();
    var gRoot = document.createElementNS("http://www.w3.org/2000/svg", "g");
    gRoot.setAttribute("class", "rmc-pkg-graph-transform");

    var defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    var marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
    marker.setAttribute("id", markerId);
    marker.setAttribute("markerWidth", "8");
    marker.setAttribute("markerHeight", "8");
    marker.setAttribute("refX", "6");
    marker.setAttribute("refY", "4");
    marker.setAttribute("orient", "auto");
    var mp = document.createElementNS("http://www.w3.org/2000/svg", "path");
    mp.setAttribute("d", "M0,0 L8,4 L0,8 z");
    mp.setAttribute("fill", tok("--color-base-500", "#64748b"));
    marker.appendChild(mp);
    defs.appendChild(marker);
    svg.appendChild(defs);

    var edges = document.createElementNS("http://www.w3.org/2000/svg", "g");
    edges.setAttribute("stroke", tok("--color-base-400", "#94a3b8"));
    edges.setAttribute("stroke-width", "1.5");
    edges.setAttribute("fill", "none");
    edges.setAttribute("marker-end", "url(#" + markerId + ")");

    var nodes = document.createElementNS("http://www.w3.org/2000/svg", "g");

    var cx = 210;
    var cy = 130;
    var nodeW = 100;
    var nodeH = 36;
    var colLeft = 24;
    var colRight = 396 - nodeW - 24;

    function addNode(id, x, y, label, fill, stroke) {
      var rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", x);
      rect.setAttribute("y", y);
      rect.setAttribute("rx", "6");
      rect.setAttribute("width", nodeW);
      rect.setAttribute("height", nodeH);
      rect.setAttribute("fill", fill || tok("--color-base-100", "#f1f5f9"));
      rect.setAttribute("stroke", stroke || tok("--color-base-500", "#64748b"));
      rect.setAttribute("stroke-width", "1");
      rect.setAttribute("id", "n-" + sanitizeId(id) + "-" + markerId);

      var text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      text.setAttribute("x", x + nodeW / 2);
      text.setAttribute("y", y + nodeH / 2 + 4);
      text.setAttribute("text-anchor", "middle");
      text.setAttribute("font-size", "10");
      text.setAttribute("font-family", "system-ui, sans-serif");
      text.setAttribute("fill", tok("--color-base-900", "#0f172a"));
      var display =
        String(label).length > 18
          ? String(label).slice(0, 16) + "…"
          : String(label);
      text.textContent = display;

      nodes.appendChild(rect);
      nodes.appendChild(text);
      return { cx: x + nodeW / 2, cy: y + nodeH / 2, w: nodeW, h: nodeH };
    }

    function line(x1, y1, x2, y2) {
      var ln = document.createElementNS("http://www.w3.org/2000/svg", "line");
      ln.setAttribute("x1", x1);
      ln.setAttribute("y1", y1);
      ln.setAttribute("x2", x2);
      ln.setAttribute("y2", y2);
      edges.appendChild(ln);
    }

    var upCenters = [];
    var spacing = Math.min(48, 200 / Math.max(1, up.length));
    var startY = cy - ((up.length - 1) * spacing) / 2;
    for (var i = 0; i < up.length; i++) {
      var pid = up[i];
      var pos = addNode(
        "u-" + i,
        colLeft,
        startY + i * spacing - nodeH / 2,
        pid,
        "#e0f2fe",
        "#0284c7"
      );
      upCenters.push(pos);
    }

    var centerPos = addNode(
      "c",
      cx - nodeW / 2,
      cy - nodeH / 2,
      centerId,
      "#fef3c7",
      "#d97706"
    );

    var downCenters = [];
    spacing = Math.min(48, 200 / Math.max(1, down.length));
    startY = cy - ((down.length - 1) * spacing) / 2;
    for (var j = 0; j < down.length; j++) {
      var did = down[j];
      var dpos = addNode(
        "d-" + j,
        colRight,
        startY + j * spacing - nodeH / 2,
        did,
        "#ecfdf5",
        "#059669"
      );
      downCenters.push(dpos);
    }

    /* pos.cx / pos.cy are node centers; connect right edge of upstream to left edge of center, etc. */
    for (var ui = 0; ui < upCenters.length; ui++) {
      var uc = upCenters[ui];
      line(
        uc.cx + uc.w / 2,
        uc.cy,
        centerPos.cx - centerPos.w / 2,
        centerPos.cy
      );
    }
    for (var dj = 0; dj < downCenters.length; dj++) {
      var dc = downCenters[dj];
      line(
        centerPos.cx + centerPos.w / 2,
        centerPos.cy,
        dc.cx - dc.w / 2,
        dc.cy
      );
    }

    gRoot.appendChild(edges);
    gRoot.appendChild(nodes);
    svg.appendChild(gRoot);
    wrap.appendChild(svg);
    mount.appendChild(wrap);

    var scale = 1;
    var tx = 0;
    var ty = 0;

    function applyTransform() {
      gRoot.setAttribute(
        "transform",
        "translate(" + tx + "," + ty + ") scale(" + scale + ")"
      );
    }
    applyTransform();

    var dragging = false;
    var lastX = 0;
    var lastY = 0;

    function endDrag() {
      dragging = false;
      wrap.style.cursor = "grab";
      document.removeEventListener("mouseup", endDrag);
    }

    wrap.addEventListener("mousedown", function (e) {
      if (e.button !== 0) return;
      dragging = true;
      wrap.style.cursor = "grabbing";
      lastX = e.clientX;
      lastY = e.clientY;
      document.addEventListener("mouseup", endDrag);
      document.addEventListener("mouseleave", endDrag);
      e.preventDefault();
    });
    wrap.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      tx += e.clientX - lastX;
      ty += e.clientY - lastY;
      lastX = e.clientX;
      lastY = e.clientY;
      applyTransform();
    });
    wrap.addEventListener(
      "wheel",
      function (e) {
        e.preventDefault();
        var delta = e.deltaY > 0 ? -0.08 : 0.08;
        scale = clamp(scale + delta, 0.5, 2.5);
        applyTransform();
      },
      { passive: false }
    );
  }

  global.RmcPackageDependencyGraph = {
    render: renderPackageDependencyGraph,
  };
})(typeof window !== "undefined" ? window : this);
