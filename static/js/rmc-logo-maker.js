/* ============================================================================
 * rmc-logo-maker.js — on-the-fly monogram logo maker for the branding studio.
 *
 * Owner: "give the user the ability to design and create a logo on the fly."
 * Draws a clean monogram (initials + brand colour + shape) to a <canvas>, live.
 * "Download PNG" hands the user a file; "Use this logo" exports the canvas to a
 * PNG and feeds it straight into the studio's EXISTING logo-upload form
 * (#rmc-day1-logo-upload-input / [data-rmc-day1-logo-upload-form]) — reusing its
 * validation, persistence, and brand-colour seeding. No new endpoint, no SVG
 * (the upload only accepts raster), and the Download path always works even when
 * DataTransfer/canvas.toBlob is unavailable.
 * ========================================================================== */
(function () {
  "use strict";

  function $(sel, root) { return (root || document).querySelector(sel); }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function drawLogo(canvas, opts) {
    var ctx = canvas.getContext("2d");
    if (!ctx) { return; }
    var S = canvas.width;
    ctx.clearRect(0, 0, S, S);
    var pad = Math.round(S * 0.06);
    var x = pad, y = pad, w = S - pad * 2, h = S - pad * 2;
    ctx.fillStyle = opts.color || "#4f46e5";
    ctx.beginPath();
    if (opts.shape === "circle") {
      ctx.arc(S / 2, S / 2, w / 2, 0, Math.PI * 2);
    } else if (opts.shape === "square") {
      ctx.rect(x, y, w, h);
    } else {
      roundRect(ctx, x, y, w, h, Math.round(w * 0.24));
    }
    ctx.fill();
    var text = ((opts.initials || "S").trim() || "S").slice(0, 3).toUpperCase();
    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    var fs = text.length >= 3 ? S * 0.32 : (text.length === 2 ? S * 0.42 : S * 0.5);
    ctx.font = "800 " + Math.round(fs) + "px Inter, system-ui, -apple-system, 'Segoe UI', sans-serif";
    ctx.fillText(text, S / 2, S / 2 + S * 0.02);
  }

  function init(root) {
    var canvas = $("[data-rmc-logo-maker-canvas]", root);
    if (!canvas || root.__rmcLogoMaker) { return; }
    root.__rmcLogoMaker = true;

    var initialsInput = $("[data-rmc-logo-maker-initials]", root);
    var colorInput = $("[data-rmc-logo-maker-colorpick]", root);
    var statusEl = $("[data-rmc-logo-maker-status]", root);

    function setStatus(msg) { if (statusEl) { statusEl.textContent = msg; } }

    function opts() {
      var shapeEl = root.querySelector("[data-rmc-logo-maker-shape]:checked");
      return {
        initials: (initialsInput && initialsInput.value) ||
          root.getAttribute("data-rmc-logo-maker-initial") || "S",
        color: (colorInput && colorInput.value) ||
          root.getAttribute("data-rmc-logo-maker-color") || "#4f46e5",
        shape: (shapeEl && shapeEl.value) || "squircle"
      };
    }

    function redraw() { drawLogo(canvas, opts()); }
    redraw();

    if (initialsInput) { initialsInput.addEventListener("input", redraw); }
    if (colorInput) { colorInput.addEventListener("input", redraw); }
    var shapes = root.querySelectorAll("[data-rmc-logo-maker-shape]");
    for (var i = 0; i < shapes.length; i++) { shapes[i].addEventListener("change", redraw); }

    var dl = $("[data-rmc-logo-maker-download]", root);
    if (dl) {
      dl.addEventListener("click", function () {
        try {
          var a = document.createElement("a");
          a.href = canvas.toDataURL("image/png");
          a.download = "school-logo.png";
          document.body.appendChild(a);
          a.click();
          a.remove();
          setStatus("Downloaded — you can upload it above any time.");
        } catch (e) {
          setStatus("Could not export the image in this browser.");
        }
      });
    }

    var use = $("[data-rmc-logo-maker-use]", root);
    if (use) {
      use.addEventListener("click", function () {
        if (!canvas.toBlob || typeof DataTransfer === "undefined" || typeof File === "undefined") {
          setStatus("This browser can't auto-apply — use Download, then upload it above.");
          return;
        }
        setStatus("Generating your logo…");
        canvas.toBlob(function (blob) {
          var input = document.getElementById("rmc-day1-logo-upload-input");
          var form = document.querySelector("[data-rmc-day1-logo-upload-form]");
          if (!blob || !input || !form) {
            setStatus("Saved — use Download, then upload it above to apply.");
            return;
          }
          try {
            var file = new File([blob], "school-logo.png", { type: "image/png" });
            var dt = new DataTransfer();
            dt.items.add(file);
            input.files = dt.files;
            input.dispatchEvent(new Event("change", { bubbles: true }));
            setStatus("Applying your new logo…");
            if (typeof form.requestSubmit === "function") { form.requestSubmit(); } else { form.submit(); }
          } catch (e) {
            setStatus("Couldn't auto-apply — use Download, then upload it above.");
          }
        }, "image/png");
      });
    }
  }

  function boot() {
    var roots = document.querySelectorAll("[data-rmc-logo-maker]");
    for (var i = 0; i < roots.length; i++) { init(roots[i]); }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
