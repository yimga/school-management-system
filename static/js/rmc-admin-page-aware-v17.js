(function () {
  "use strict";

  function fieldName(row) {
    var input = row.querySelector("input[name], select[name], textarea[name]");
    return input ? String(input.name || "").toLowerCase() : "";
  }

  function classifyRow(row) {
    if (!row || row.dataset.rmcFieldSpan) return;
    var name = fieldName(row);
    var fields = row.querySelectorAll("input[name], select[name], textarea[name]");
    var span = "standard";
    if (
      row.querySelector("textarea, .selector, .related-widget-wrapper.multiple") ||
      fields.length > 2 ||
      /json|payload|content|description|body|address|permissions|groups|legal_links|social_links|contacts|app_badges/.test(name)
    ) span = "full";
    else if (row.querySelector('input[type="url"], input[type="file"], .select2-container') || /email|url|domain|path|identifier/.test(name)) span = "wide";
    else if (row.querySelector('input[type="checkbox"], input[type="radio"], input[type="date"], input[type="time"], input[type="number"]') || /year|status|active|enabled|mode|type|code/.test(name)) span = "short";
    row.dataset.rmcFieldSpan = span;
  }

  function classifyFieldsets(root) {
    var sets = root.querySelectorAll("[data-rmc-admin-fieldset], .site-settings-section");
    sets.forEach(function (fieldset) {
      var rows = fieldset.querySelectorAll(":scope .form-row");
      rows.forEach(classifyRow);
      var wide = fieldset.querySelector('[data-rmc-field-span="full"], textarea, .selector, .inline-group');
      if (wide || rows.length > 8) fieldset.dataset.rmcFieldsetSpan = "full";
    });
    var total = root.querySelectorAll(".form-row").length;
    root.dataset.rmcFormDensity = total >= 30 ? "long" : total >= 14 ? "medium" : "short";
  }

  function buildPageRail(root) {
    var nav = root.querySelector("[data-rmc-onthispage]");
    if (!nav || nav.dataset.rmcBuilt === "1") return;
    var headings = root.querySelectorAll("[data-rmc-admin-fieldset-heading], .site-settings-section h2");
    var used = {};
    headings.forEach(function (heading, index) {
      var label = String(heading.textContent || "").trim();
      if (!label) return;
      var id = heading.id || "rmc-admin-section-" + (index + 1);
      while (used[id]) id += "-x";
      used[id] = true;
      heading.id = id;
      var link = document.createElement("a");
      link.href = "#" + id;
      link.className = "rmc-onthispage__link";
      link.textContent = label;
      nav.appendChild(link);
    });
    nav.dataset.rmcBuilt = "1";
  }

  function dedupeSidebar(root) {
    // NOT [data-rmc-shell-sidebar]: that is a shell-ROOT mode flag
    // ("offcanvas"), set on .rmc-app-shell by _pages/rmc-app-shell.js, so it
    // names the whole page. Selecting on it made this dedupe walk all 693
    // anchors on the admin index and hide every catalog tile as a duplicate
    // of an earlier link -- section headers over empty bodies, and on the
    // app-index a card title plus its Changelist link (same href) both gone,
    // while "+ Add" survived because its href differs.
    var nav = root.querySelector(".rmc-app-shell__sidebar") ||
      root.querySelector("#nav-sidebar") ||
      root.querySelector("[data-rmc-sidebar]");
    if (!nav) return;
    var seen = {};
    nav.querySelectorAll("a[href]").forEach(function (link) {
      var key = "";
      try {
        var url = new URL(link.href, window.location.href);
        key = (url.pathname.replace(/\/+$/, "") || "/") + url.search;
      } catch (ignore) { key = link.href; }
      if (!key || !seen[key]) { seen[key] = true; return; }
      // Only ever hide a real nav ITEM. The old `|| link` fallback hid the
      // ANCHOR when it had no list ancestor, which is every content link on
      // the page -- a dedupe for a nav list must not touch main content.
      var item = link.closest("li");
      if (!item || !nav.contains(item)) return;
      item.hidden = true;
      item.dataset.rmcDuplicateNav = "1";
    });
  }

  function wireSaveMenus(root) {
    var rows = root.querySelectorAll('[data-rmc-admin-submit-contract="sticky-safe-actions"]');
    for (var i = 1; i < rows.length; i += 1) rows[i].remove();
    root.querySelectorAll("[data-rmc-save-compact-root]").forEach(function (menuRoot) {
      if (menuRoot.dataset.rmcSaveWired === "1") return;
      menuRoot.dataset.rmcSaveWired = "1";
      var toggle = menuRoot.querySelector("[data-rmc-save-menu-toggle]");
      var menu = menuRoot.querySelector("[data-rmc-save-menu]");
      if (!toggle || !menu) return;
      function close() { menu.hidden = true; toggle.setAttribute("aria-expanded", "false"); }
      toggle.addEventListener("click", function (event) {
        event.preventDefault(); event.stopPropagation();
        menu.hidden = !menu.hidden;
        toggle.setAttribute("aria-expanded", menu.hidden ? "false" : "true");
      });
      document.addEventListener("click", function (event) { if (!menuRoot.contains(event.target)) close(); });
      document.addEventListener("keydown", function (event) { if (event.key === "Escape") close(); });
    });
  }

  function wireBackLinks(root) {
    root.querySelectorAll(".js-admin-back").forEach(function (link) {
      if (link.dataset.rmcBackWired === "1") return;
      link.dataset.rmcBackWired = "1";
      var fallback = link.dataset.fallback || "/admin/";
      try {
        var ref = document.referrer;
        if (ref && new URL(ref).origin === window.location.origin) link.href = ref;
        else link.href = fallback;
      } catch (ignore) { link.href = fallback; }
    });
  }

  function init(root) {
    root = root || document;
    root.querySelectorAll('[data-rmc-admin-form-contract="premium-form-frame"]').forEach(classifyFieldsets);
    buildPageRail(root);
    dedupeSidebar(root);
    wireSaveMenus(root);
    wireBackLinks(root);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { init(document); });
  else init(document);
  document.addEventListener("htmx:afterSwap", function (event) { init(event.target || document); });
}());
