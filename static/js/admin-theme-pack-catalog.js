(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  }

  ready(function initThemePackCatalog() {
    var container = document.getElementById("admin-dashboard-palette-selector");
    var field = document.getElementById("id_admin_theme_pack");
    if (!container || !field) return;

    var autoApply = document.getElementById("theme-pack-auto-apply");
    var applySite = document.getElementById("theme-pack-apply-site");
    var sitePackField = document.getElementById("id_theme_pack");
    var cards = Array.prototype.slice.call(
      container.querySelectorAll(".admin-dashboard-palette-card")
    );
    var filterInput = document.getElementById("theme-pack-filter");
    var siteActiveLabel = document.getElementById("theme-pack-active-site-label");
    var adminActiveLabel = document.getElementById("theme-pack-active-admin-label");

    var wrapper = container.closest(".admin-dashboard-palette-selector-wrapper");
    var noneSelectedText = (wrapper && wrapper.dataset.noneSelected) || "None selected";
    var siteActivePrefix = (wrapper && wrapper.dataset.siteActivePrefix) || "Site active:";
    var adminActivePrefix = (wrapper && wrapper.dataset.adminActivePrefix) || "Admin active:";

    function normalizeText(value) {
      return String(value || "").toLowerCase();
    }

    function setSelected(id) {
      cards.forEach(function (card) {
        card.classList.toggle("selected", String(card.dataset.packId) === String(id));
      });
      if (field.tagName === "SELECT") field.value = id || "";
      syncCardStatusBadges();
    }

    function setCardBadgeState(card, role, enabled) {
      if (!card) return;
      var badge = card.querySelector('[data-role="' + role + '"]');
      if (badge) badge.classList.toggle("d-none", !enabled);
      if (role === "site-active") card.dataset.siteActive = enabled ? "1" : "0";
      if (role === "admin-active") card.dataset.adminActive = enabled ? "1" : "0";
    }

    function activePackNameById(packId) {
      if (!packId) return noneSelectedText;
      var activeCard = cards.find(function (card) {
        return String(card.dataset.packId || "") === String(packId);
      });
      if (!activeCard) return noneSelectedText;
      var nameNode = activeCard.querySelector(".admin-dashboard-palette-name");
      return (nameNode && nameNode.textContent ? nameNode.textContent.trim() : "") || noneSelectedText;
    }

    function updateActiveLegend(siteId, adminId) {
      if (siteActiveLabel) {
        siteActiveLabel.textContent = siteActivePrefix + " " + activePackNameById(siteId);
      }
      if (adminActiveLabel) {
        adminActiveLabel.textContent = adminActivePrefix + " " + activePackNameById(adminId);
      }
    }

    function syncCardStatusBadges() {
      var activeSiteId = sitePackField ? String(sitePackField.value || "") : "";
      var activeAdminId = String(field.value || "");
      cards.forEach(function (card) {
        var packId = String(card.dataset.packId || "");
        var siteActive = activeSiteId && packId === activeSiteId;
        var adminActive = activeAdminId && packId === activeAdminId;
        setCardBadgeState(card, "site-active", siteActive);
        setCardBadgeState(card, "admin-active", adminActive);
        card.classList.toggle("is-site-active", !!siteActive);
        card.classList.toggle("is-admin-active", !!adminActive);
        card.classList.toggle("is-active-unified", !!siteActive && !!adminActive);
      });
      updateActiveLegend(activeSiteId, activeAdminId);
    }

    function applyCard(card) {
      if (!card) return;
      setSelected(card.dataset.packId);
      if (!autoApply || autoApply.checked) {
        if (window.ThemeStudio && typeof window.ThemeStudio.applyFromDataset === "function") {
          window.ThemeStudio.applyFromDataset(card.dataset, {
            source: "theme-pack",
            setPack: true,
            setSitePack: !!(applySite && applySite.checked),
          });
        }
      }
      document.dispatchEvent(
        new CustomEvent("theme-pack-selected", {
          detail: {
            packId: card.dataset.packId,
            packSlug: card.dataset.packSlug || "",
            packName: card.querySelector(".admin-dashboard-palette-name")
              ? card.querySelector(".admin-dashboard-palette-name").textContent
              : "",
            dataset: card.dataset,
          },
        })
      );
    }

    function applyFilter(value) {
      var query = normalizeText(value).trim();
      var visible = 0;

      cards.forEach(function (card) {
        var group = card.closest(".admin-dashboard-palette-group");
        var haystack = [
          card.dataset.packSlug || "",
          card.dataset.packId || "",
          card.querySelector(".admin-dashboard-palette-name")
            ? card.querySelector(".admin-dashboard-palette-name").textContent
            : "",
          card.querySelector(".admin-dashboard-palette-desc")
            ? card.querySelector(".admin-dashboard-palette-desc").textContent
            : "",
          group ? group.getAttribute("data-group-label") || "" : "",
        ].join(" ");
        var match = query.length === 0 || normalizeText(haystack).indexOf(query) !== -1;
        card.classList.toggle("d-none", !match);
        if (match) visible += 1;
      });

      Array.prototype.slice
        .call(container.querySelectorAll(".admin-dashboard-palette-group"))
        .forEach(function (group) {
          var groupCards = group.querySelectorAll(".admin-dashboard-palette-card:not(.d-none)");
          group.classList.toggle("d-none", groupCards.length === 0);
        });

      var counter = document.getElementById("theme-pack-filter-count");
      if (!counter) {
        counter = document.createElement("span");
        counter.id = "theme-pack-filter-count";
        counter.className = "badge text-bg-secondary-subtle";
        if (filterInput && filterInput.parentElement) {
          filterInput.parentElement.appendChild(counter);
        }
      }
      counter.textContent = visible + " shown";
    }

    cards.forEach(function (card) {
      card.addEventListener("click", function () {
        applyCard(card);
      });
    });

    field.addEventListener("change", function () {
      if (field.value) setSelected(field.value);
      syncCardStatusBadges();
    });

    if (sitePackField) {
      sitePackField.addEventListener("change", syncCardStatusBadges);
    }

    if (field.value) setSelected(field.value);
    syncCardStatusBadges();

    if (window.ContrastGuard && typeof window.ContrastGuard.textColorForBackground === "function") {
      cards.forEach(function (card) {
        var bg = (card.dataset.surface || card.dataset.dashboardBg || "#f8fafc").trim();
        if (bg) {
          var fg = window.ContrastGuard.textColorForBackground(bg);
          card.style.setProperty("--card-fg", fg);
        }
      });
    }

    if (filterInput) {
      filterInput.addEventListener("input", function () {
        applyFilter(filterInput.value);
      });
      applyFilter(filterInput.value);
    }

    document.addEventListener("theme-pack-clear-selection", function () {
      setSelected("");
      syncCardStatusBadges();
    });
  });
})();
