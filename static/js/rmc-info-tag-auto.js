/**
 * Auto-attach rmc_info_tag icons to form labels from #rmc-page-field-manifest.
 */
(function () {
  function parseManifest() {
    var el = document.getElementById("rmc-page-field-manifest");
    if (!el || !el.textContent) return [];
    try {
      var data = JSON.parse(el.textContent);
      return Array.isArray(data) ? data : [];
    } catch (e) {
      return [];
    }
  }

  function findControl(names) {
    for (var i = 0; i < names.length; i++) {
      var n = names[i];
      if (!n) continue;
      var byName = document.querySelector(
        'input[name="' + n + '"], select[name="' + n + '"], textarea[name="' + n + '"]'
      );
      if (byName) return byName;
      var byId = document.getElementById(n);
      if (byId) return byId;
    }
    return null;
  }

  function findLabel(control) {
    if (!control || !control.id) return null;
    var label = document.querySelector('label[for="' + control.id + '"]');
    if (label) return label;
    var parent = control.closest(".mb-3, .form-group, .field, .rmc-form-field");
    if (parent) {
      label = parent.querySelector("label");
      if (label) return label;
    }
    return null;
  }

  function hasInfoTag(label) {
    return label && label.querySelector(".rmc-info-tag");
  }

  function createTag(entity, field) {
    var wrap = document.createElement("span");
    wrap.className = "rmc-info-tag rmc-info-tag--auto";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "rmc-info-tag__btn btn btn-link p-0 align-baseline";
    btn.setAttribute("data-bs-toggle", "popover");
    btn.setAttribute("data-bs-trigger", "focus");
    btn.setAttribute("data-bs-placement", "top");
    btn.setAttribute("data-rmc-info-entity", entity);
    btn.setAttribute("data-rmc-info-field", field);
    btn.setAttribute("aria-label", "More information");
    var icon = document.createElement("i");
    icon.className = "bi bi-info-circle";
    icon.setAttribute("aria-hidden", "true");
    btn.appendChild(icon);
    wrap.appendChild(btn);
    return wrap;
  }

  function wireEntry(entry) {
    if (!entry || !entry.entity || !entry.field) return;
    var names = entry.names;
    if (typeof names === "string") {
      try {
        names = JSON.parse(names);
      } catch (e) {
        names = [names];
      }
    }
    if (!Array.isArray(names)) return;
    var control = findControl(names);
    var label = findLabel(control);
    if (!label || hasInfoTag(label)) return;
    label.appendChild(document.createTextNode(" "));
    label.appendChild(createTag(entry.entity, entry.field));
  }

  function init() {
    var manifest = parseManifest();
    manifest.forEach(wireEntry);
    if (typeof window.bootstrap !== "undefined" && bootstrap.Popover) {
      document
        .querySelectorAll(".rmc-info-tag--auto [data-bs-toggle='popover']")
        .forEach(function (el) {
          if (!bootstrap.Popover.getInstance(el)) {
            new bootstrap.Popover(el, { container: "body", sanitize: true });
          }
        });
    }
    if (typeof document.dispatchEvent === "function") {
      document.dispatchEvent(new CustomEvent("rmc-info-tag-auto-ready"));
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
