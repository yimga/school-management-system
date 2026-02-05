/**
 * Interactive color wheel (Pickr) alongside editable hex code.
 * Sync: Pickr <-> hex input; swatch reflects current color.
 */
(function () {
  var HEX_RE = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

  function isValidHex(str) {
    if (!str || typeof str !== "string") return false;
    str = str.trim();
    if (!str.startsWith("#")) str = "#" + str;
    return HEX_RE.test(str);
  }

  function normalizeHex(str) {
    if (!str || typeof str !== "string") return "#ffffff";
    str = str.trim().toLowerCase();
    if (!str.startsWith("#")) str = "#" + str;
    if (str.length === 4) str = "#" + str.slice(1).split("").map(function (c) { return c + c; }).join("");
    return str;
  }

  function init() {
    if (typeof Pickr === "undefined") return;

    document.querySelectorAll(".color-input-with-preview").forEach(function (wrap) {
      if (wrap.dataset.pickrInit) return;
      var btn = wrap.querySelector(".color-pickr-trigger");
      var input = wrap.querySelector("input[type=text].color-input-with-preview-hex");
      if (!btn || !input) return;

      var initial = wrap.dataset.initial || input.value || "#ffffff";
      var val = normalizeHex(initial);
      input.value = val;
      btn.style.backgroundColor = val;

      var pickr = Pickr.create({
        el: btn,
        theme: "classic",
        default: val,
        useAsButton: true,
        defaultRepresentation: "HEX",
        lockOpacity: true,
        components: {
          preview: true,
          opacity: false,
          hue: true,
          interaction: {
            hex: true,
            rgba: false,
            hsla: false,
            hsva: false,
            cmyk: false,
            input: true,
            clear: false,
            save: true
          }
        }
      });

      function colorToHex(color) {
        if (!color) return "#ffffff";
        try {
          var arr = color.toHEXA ? color.toHEXA() : (color.toRGBA && color.toRGBA());
          if (Array.isArray(arr) && arr.length >= 3) {
            return "#" + arr.slice(0, 3).map(function (n) {
              if (typeof n === "string" && /^[0-9a-fA-F]{2}$/.test(n)) return n.toLowerCase();
              var x = typeof n === "number" ? Math.round(n) : parseInt(n, 10);
              if (isNaN(x)) x = 0;
              x = x < 0 ? 0 : x > 255 ? 255 : x;
              var s = x.toString(16);
              return s.length === 1 ? "0" + s : s;
            }).join("");
          }
          if (typeof color.toString === "function") {
            var s = color.toString();
            if (s && s.indexOf("#") === 0 && s.length >= 7) return s.slice(0, 7);
          }
          return "#ffffff";
        } catch (e) { return "#ffffff"; }
      }

      pickr.on("change", function (color) {
        if (!color) return;
        var hex = colorToHex(color);
        input.value = hex;
        btn.style.backgroundColor = hex;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });

      pickr.on("save", function (color) {
        if (color) {
          var hex = colorToHex(color);
          input.value = hex;
          btn.style.backgroundColor = hex;
          input.dispatchEvent(new Event("change", { bubbles: true }));
        }
        pickr.hide();
      });

      var debounce;
      input.addEventListener("input", function () {
        clearTimeout(debounce);
        debounce = setTimeout(function () {
          var v = input.value.trim();
          if (!v.startsWith("#")) v = "#" + v;
          if (isValidHex(v)) {
            var norm = normalizeHex(v);
            pickr.setColor(norm);
            btn.style.backgroundColor = norm;
          }
        }, 300);
      });

      input.addEventListener("change", function () {
        var v = normalizeHex(input.value);
        if (isValidHex(v)) {
          pickr.setColor(v);
          btn.style.backgroundColor = v;
        }
      });

      wrap.dataset.pickrInit = "true";
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
