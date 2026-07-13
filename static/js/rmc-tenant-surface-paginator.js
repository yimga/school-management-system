(function () {
  "use strict";

  // rmc-tenant-surface-paginator: tenant-wide long-page section navigator.
  // Emits data-rmc-surface-page and data-rmc-surface-scroll-zone markers.
  var ROOT_SELECTORS = [
    '[data-rmc-django-surface-canvas="tenant-backend"]',
    '[data-rmc-page="studio-os"]',
    '.tp-canvas-body[data-rmc-scroll-policy="paginate"]',
    '.portal-page-body[data-rmc-scroll-policy="paginate"]',
    '[data-rmc-operational-workbench="1"]',
    '[data-page-archetype="operational-workbench"]'
  ];

  var MAJOR_SECTION_SELECTOR = [
    ':scope > section',
    ':scope > article',
    ':scope > main',
    ':scope > form',
    ':scope > .studio-os__card',
    ':scope > .rmc-command-surface',
    ':scope > .rmc-command-panel',
    ':scope > .rmc-wcx-surface',
    ':scope > .card',
    ':scope > .row',
    ':scope > .container-fluid'
  ].join(",");

  var OVERSIZE_PANEL_SELECTOR = [
    '.table-responsive',
    '.results',
    '[data-rmc-table]',
    '.rmc-data-table-wrap',
    '.studio-os-activity-list',
    '.rmc-admin-bento__panel',
    '.rmc-command-panel',
    '.rmc-command-surface',
    '.rmc-wcx-surface',
    '.card'
  ].join(",");

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  }

  function isTenantLikePage() {
    var body = document.body;
    if (!body) {
      return false;
    }
    if (body.classList.contains("marketing-surface")) {
      return false;
    }
    return Boolean(
      body.classList.contains("portal-body-with-layout") ||
        body.classList.contains("backend-shell") ||
        document.querySelector('[data-rmc-django-surface-canvas="tenant-backend"], [data-rmc-page="studio-os"]')
    );
  }

  function isVisible(el) {
    if (!el || el.hidden || el.getAttribute("aria-hidden") === "true") {
      return false;
    }
    if (el.classList && el.classList.contains("visually-hidden")) {
      return false;
    }
    var rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function hasExcludedPreview(el) {
    return Boolean(
      el.matches &&
        el.matches(
          '.rmc-live-preview-contract, [data-rmc-live-preview-contract="1"], .rmc-dashboard-preview-shell, .rmc-studio-experience-preview, .reportcard-builder-preview, .theme-preview-section'
        )
    );
  }

  function normalizedText(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function labelForSection(section, index) {
    var heading = section.querySelector("h1, h2, h3, [data-rmc-section-title], [aria-label]");
    var label = "";
    if (heading) {
      label = normalizedText(
        heading.getAttribute("data-rmc-section-title") ||
          heading.getAttribute("aria-label") ||
          heading.textContent
      );
    }
    if (!label) {
      label = normalizedText(section.getAttribute("aria-label") || section.getAttribute("data-page-archetype"));
    }
    if (!label) {
      label = "Section";
    }
    if (label.length > 42) {
      label = label.slice(0, 39).trim() + "...";
    }
    return "Page " + (index + 1) + ": " + label;
  }

  function rootAlreadyHandled(root) {
    return root.dataset && root.dataset.rmcSurfacePagesReady === "1";
  }

  function meaningfulChildren(root) {
    var children = [];
    try {
      children = Array.prototype.slice.call(root.querySelectorAll(MAJOR_SECTION_SELECTOR));
    } catch (error) {
      children = Array.prototype.slice.call(root.children || []);
    }
    return children.filter(function (child) {
      if (!isVisible(child)) {
        return false;
      }
      if (child.matches && child.matches("script, style, link, template, nav.rmc-surface-page-nav")) {
        return false;
      }
      if (child.closest && child.closest(".rmc-surface-page-nav")) {
        return false;
      }
      var rect = child.getBoundingClientRect();
      var hasHeading = Boolean(child.querySelector("h1, h2, h3, [data-rmc-section-title]"));
      return rect.height >= 120 || hasHeading || child.children.length >= 3;
    });
  }

  function shouldPaginate(root, sections) {
    if (sections.length < 4) {
      return false;
    }
    var scrollContainer = document.querySelector("#main-content") || root;
    var viewportHeight = scrollContainer.clientHeight || window.innerHeight || 720;
    return root.scrollHeight > viewportHeight * 1.2 || sections.length >= 6;
  }

  function ensureId(el, prefix, index) {
    if (el.id) {
      return el.id;
    }
    var id = prefix + "-" + (index + 1);
    var suffix = 1;
    while (document.getElementById(id)) {
      suffix += 1;
      id = prefix + "-" + (index + 1) + "-" + suffix;
    }
    el.id = id;
    return id;
  }

  function buildNav(root, sections) {
    var nav = document.createElement("nav");
    nav.className = "rmc-surface-page-nav";
    nav.setAttribute("aria-label", "Page sections");
    nav.dataset.rmcSurfacePageNav = "1";

    var label = document.createElement("span");
    label.className = "rmc-surface-page-nav__label";
    label.textContent = sections.length + " pages";
    nav.appendChild(label);

    sections.forEach(function (section, index) {
      var id = ensureId(section, "rmc-surface-page", index);
      var text = labelForSection(section, index);
      section.dataset.rmcSurfacePage = String(index + 1);
      section.dataset.rmcSurfacePageLabel = "Page " + (index + 1) + " of " + sections.length;
      section.dataset.rmcSurfacePageTitle = text;

      var button = document.createElement("button");
      button.type = "button";
      button.className = "rmc-surface-page-nav__button";
      button.textContent = text;
      button.setAttribute("aria-controls", id);
      button.addEventListener("click", function () {
        section.scrollIntoView({ behavior: "smooth", block: "start" });
        Array.prototype.forEach.call(nav.querySelectorAll("[aria-current]"), function (active) {
          active.removeAttribute("aria-current");
        });
        button.setAttribute("aria-current", "true");
      });
      nav.appendChild(button);
    });

    var anchor = root.firstElementChild;
    if (anchor && anchor.classList && anchor.classList.contains("visually-hidden")) {
      anchor = anchor.nextElementSibling;
    }
    root.insertBefore(nav, anchor || root.firstChild);
  }

  function markOversizePanels(root) {
    Array.prototype.forEach.call(root.querySelectorAll(OVERSIZE_PANEL_SELECTOR), function (panel) {
      if (!isVisible(panel) || hasExcludedPreview(panel)) {
        return;
      }
      if (panel.closest("[data-rmc-surface-scroll-zone]")) {
        return;
      }
      var hasLongTable = Boolean(panel.querySelector("table tbody tr:nth-child(12), .table tbody tr:nth-child(12)"));
      var manyChildren = panel.children && panel.children.length >= 14;
      var tooTall = panel.scrollHeight > Math.max(720, window.innerHeight * 0.72);
      if (hasLongTable || manyChildren || tooTall) {
        panel.dataset.rmcSurfaceScrollZone = "bounded";
        if (!panel.hasAttribute("tabindex")) {
          panel.setAttribute("tabindex", "0");
        }
      }
    });
  }

  function collectRoots() {
    var main = document.querySelector("#main-content");
    var roots = [];
    ROOT_SELECTORS.forEach(function (selector) {
      Array.prototype.forEach.call(document.querySelectorAll(selector), function (root) {
        if (!isVisible(root)) {
          return;
        }
        if (main && !main.contains(root) && root !== main) {
          return;
        }
        roots.push(root);
      });
    });
    return roots.filter(function (root, index) {
      if (roots.indexOf(root) !== index) {
        return false;
      }
      if (
        roots.some(function (other) {
          return (
            other !== root &&
            root.contains(other) &&
            other.matches('[data-rmc-django-surface-canvas="tenant-backend"], [data-rmc-page="studio-os"]')
          );
        })
      ) {
        return false;
      }
      return !roots.some(function (other) {
        return other !== root && other.contains(root) && other.matches('[data-rmc-django-surface-canvas="tenant-backend"], [data-rmc-page="studio-os"]');
      });
    });
  }

  function hydrateRoot(root) {
    if (rootAlreadyHandled(root)) {
      return;
    }
    markOversizePanels(root);
    var sections = meaningfulChildren(root);
    if (!shouldPaginate(root, sections)) {
      return;
    }
    root.classList.add("rmc-tenant-surface-pages");
    root.dataset.rmcSurfacePagesReady = "1";
    buildNav(root, sections.slice(0, 16));
  }

  ready(function () {
    if (!isTenantLikePage()) {
      return;
    }
    collectRoots().forEach(hydrateRoot);
  });
})();
