(function () {
  "use strict";

  function onReady(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  function initBackendCharts() {
    if (typeof window.Chart === "undefined" || !window.DashboardChartsShared) return;
    var shared = window.DashboardChartsShared;
    var charts = {};
    var chartIds = ["backendEnrollmentTrendChart", "backendFinanceStatusChart"];

    chartIds.forEach(function (chartId) {
      var configEl = document.querySelector('[data-chart-config="' + chartId + '"]');
      if (!configEl) return;

      try {
        var config = JSON.parse(configEl.textContent || "{}");
        var hasLabels = config.data && Array.isArray(config.data.labels) && config.data.labels.length > 0;
        var ds = hasLabels && config.data.datasets ? config.data.datasets[0] : null;
        var hasValues = !ds || !Array.isArray(ds.data) || ds.data.some(function (v) { return (v || 0) > 0; });

        if (hasLabels && hasValues) {
          charts[chartId] = shared.createChart(chartId, config);
        } else {
          var emptyEl = document.querySelector('[data-chart-empty="' + chartId + '"]');
          if (emptyEl) emptyEl.classList.remove("d-none");
          var canvas = document.getElementById(chartId);
          if (canvas) canvas.style.display = "none";
        }
      } catch (err) {
        console.warn("Backend chart init:", chartId, err);
      }
    });

    document.querySelectorAll("[data-chart-export]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = this.getAttribute("data-chart-export");
        if (id && charts[id]) {
          shared.exportChartToPng(charts[id], "backend-chart-" + id + ".png");
        }
      });
    });
  }

  function initBackendCommandPalette() {
    var paletteEl = document.getElementById("backendCommandPalette");
    var inputEl = document.getElementById("backendCommandInput");
    var resultsEl = document.getElementById("backendCommandResults");
    var dataEl = document.getElementById("backend-command-palette-data");
    if (!paletteEl || !inputEl || !resultsEl || !dataEl) return;

    var triggerEls = document.querySelectorAll(".js-open-backend-command");
    var commands = [];
    try {
      commands = JSON.parse(dataEl.textContent || "[]");
    } catch (err) {
      commands = [];
    }
    if (!Array.isArray(commands)) commands = [];

    var activeQueryResults = [];
    var selectedIndex = 0;
    var previousFocusedElement = null;

    function isTypingContext(target) {
      if (!target) return false;
      var tag = (target.tagName || "").toLowerCase();
      if (target.isContentEditable) return true;
      return tag === "input" || tag === "textarea" || tag === "select";
    }

    function escapeHtml(value) {
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function closePalette() {
      paletteEl.classList.remove("is-open");
      paletteEl.setAttribute("aria-hidden", "true");
      if (previousFocusedElement && typeof previousFocusedElement.focus === "function") {
        previousFocusedElement.focus();
      }
    }

    function renderResults(query, preserveSelection) {
      var normalized = String(query || "").trim().toLowerCase();
      var items = commands.filter(function (item) {
        if (!normalized) return true;
        return String(item.label || "").toLowerCase().indexOf(normalized) >= 0;
      });
      activeQueryResults = items;
      if (!preserveSelection) selectedIndex = 0;
      if (selectedIndex >= items.length && items.length > 0) selectedIndex = items.length - 1;
      if (selectedIndex < 0) selectedIndex = 0;

      if (!items.length) {
        resultsEl.innerHTML = '<div class="backend-cmd-empty">No matching command.</div>';
        return;
      }

      var lead = normalized ? "" : '<div class="backend-cmd-empty text-start py-2">Available commands</div>';
      resultsEl.innerHTML = lead + items.map(function (item, index) {
        var label = escapeHtml(item.label || "Command");
        var href = String(item.url || "#");
        var selected = index === selectedIndex ? " backend-cmd-item--selected" : "";
        return '<a class="backend-cmd-item' + selected + '" href="' + href + '" data-index="' + index + '"><span>' + label + "</span><kbd>Enter</kbd></a>";
      }).join("");

      var selectedEl = resultsEl.querySelector(".backend-cmd-item--selected");
      if (selectedEl) selectedEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    function openPalette() {
      previousFocusedElement = document.activeElement;
      paletteEl.classList.add("is-open");
      paletteEl.setAttribute("aria-hidden", "false");
      renderResults(inputEl.value || "");
      setTimeout(function () { inputEl.focus(); }, 0);
    }

    triggerEls.forEach(function (trigger) {
      trigger.addEventListener("click", function (event) {
        event.preventDefault();
        openPalette();
      });
    });

    paletteEl.querySelectorAll("[data-cmd-close]").forEach(function (node) {
      node.addEventListener("click", closePalette);
    });

    inputEl.addEventListener("input", function () {
      renderResults(inputEl.value);
    });

    inputEl.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        var item = activeQueryResults[selectedIndex];
        if (item && item.url) window.location.href = item.url;
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        if (activeQueryResults.length) {
          selectedIndex = (selectedIndex + 1) % activeQueryResults.length;
          renderResults(inputEl.value, true);
        }
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        if (activeQueryResults.length) {
          selectedIndex = selectedIndex <= 0 ? activeQueryResults.length - 1 : selectedIndex - 1;
          renderResults(inputEl.value, true);
        }
      } else if (event.key === "Escape") {
        event.preventDefault();
        closePalette();
      }
    });

    resultsEl.addEventListener("click", function (event) {
      var item = event.target.closest(".backend-cmd-item");
      if (item && activeQueryResults[Number(item.getAttribute("data-index"))]) {
        event.preventDefault();
        var cmd = activeQueryResults[Number(item.getAttribute("data-index"))];
        if (cmd && cmd.url) window.location.href = cmd.url;
      }
    });

    // Ctrl/Cmd+K retired 2026-05-12 — that shortcut is now owned by the
    // platform-wide rmc-command-palette.js (.rmc-cmdk). This page-local palette
    // still opens via its own trigger button + closes on Escape.
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && paletteEl.classList.contains("is-open")) {
        closePalette();
      }
    });
  }

  function initOpsWatchRefresh() {
    var listEl = document.querySelector(".js-ops-watch-list");
    var stampEl = document.getElementById("backendOpsWatchUpdatedAt");
    if (!listEl) return;

    var refreshUrl = listEl.getAttribute("data-refresh-url");
    var financeUrl = listEl.getAttribute("data-finance-url") || "#";
    if (!refreshUrl) return;

    function toRelative(isoDate) {
      if (!isoDate) return "just now";
      var then = new Date(isoDate);
      if (Number.isNaN(then.getTime())) return "just now";
      var diffSec = Math.max(0, Math.round((Date.now() - then.getTime()) / 1000));
      if (diffSec < 60) return "just now";
      if (diffSec < 3600) return diffSec < 120 ? "1 min ago" : Math.floor(diffSec / 60) + " mins ago";
      return Math.floor(diffSec / 3600) + "h ago";
    }

    function itemClass(status) {
      if (status === "danger") return "backend-ops-item is-danger";
      if (status === "warn") return "backend-ops-item is-warn";
      return "backend-ops-item";
    }

    function renderOps(data) {
      var rows = [];
      var ops = Array.isArray(data.operations_watch) ? data.operations_watch : [];
      ops.forEach(function (item) {
        rows.push(
          '<div class="' + itemClass(item.status) + '" data-ops-key="' + (item.key || "") + '">' +
            '<div class="backend-ops-item-left">' +
              '<span class="backend-ops-dot"></span>' +
              '<a href="' + (item.url || "#") + '">' +
                '<i class="bi ' + (item.icon || "bi-dot") + ' me-1"></i>' + (item.label || "Item") +
              "</a>" +
            "</div>" +
            "<strong>" + (item.value || 0) + "</strong>" +
          "</div>"
        );
      });

      var financeCount = Number(data.finance_requests || 0);
      rows.push(
        '<div class="' + itemClass(financeCount > 0 ? "warn" : "ok") + '" data-ops-key="finance_requests">' +
          '<div class="backend-ops-item-left">' +
            '<span class="backend-ops-dot"></span>' +
            '<a href="' + financeUrl + '"><i class="bi bi-wallet2 me-1"></i>Finance requests</a>' +
          "</div>" +
          "<strong>" + financeCount + "</strong>" +
        "</div>"
      );

      listEl.innerHTML = rows.join("");
      if (stampEl) stampEl.textContent = "Live - " + toRelative(data.updated_at);
      document.dispatchEvent(new Event("backend:content-updated"));
    }

    function refreshOps() {
      fetch(refreshUrl, { credentials: "same-origin" })
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (payload) {
          if (!payload || payload.success !== true) return;
          renderOps(payload);
        })
        .catch(function () {});
    }

    setInterval(refreshOps, 60000);
    refreshOps();
  }

  function initConditionalScroll() {
    var selectors = [
      ".backend-v2-main-grid .dashboard-card-scroll",
      ".backend-v2-rail .js-ops-watch-list",
      ".backend-v2-rail [data-widget-id=\"backend-quick-links\"] .backend-quick-links-list",
      ".backend-v2-rail [data-widget-id=\"backend-planner\"] .backend-planner-list"
    ];

    function refresh() {
      selectors.forEach(function (selector) {
        document.querySelectorAll(selector).forEach(function (el) {
          if (!el) return;
          var overflowing = (el.scrollHeight - el.clientHeight) > 4;
          el.classList.toggle("is-overflowing", overflowing);
        });
      });
    }

    refresh();
    window.addEventListener("resize", refresh);
    document.addEventListener("backend:content-updated", refresh);
    setTimeout(refresh, 250);
    setTimeout(refresh, 1000);
  }

  function ensureBackendCoreWidgetsVisible() {
    var ids = ["backend-recent-activity", "backend-top-performing", "backend-attendance-today"];

    function ensurePlacement(root) {
      var grid = root ? root.querySelector(".backend-v2-main-grid") : null;
      if (!grid) return;
      ids.forEach(function (id) {
        var el = root.querySelector('[data-widget-id="' + id + '"]');
        if (el && el.parentElement !== grid) grid.appendChild(el);
      });
    }

    function ensureVisible() {
      var root = document.getElementById("dashboard-layout");
      if (!root) return;
      ensurePlacement(root);
      ids.forEach(function (id) {
        var el = root.querySelector('[data-widget-id="' + id + '"]');
        if (el && (el.classList.contains("dash-widget-hidden") || el.style.display === "none")) {
          el.classList.remove("dash-widget-hidden");
          el.style.display = "";
        }
      });
    }

    ensureVisible();
    var attempts = 0;
    var t = setInterval(function () {
      ensureVisible();
      attempts += 1;
      if (attempts >= 10) clearInterval(t);
    }, 1000);
  }

  onReady(function () {
    initBackendCharts();
    initBackendCommandPalette();
    initOpsWatchRefresh();
    ensureBackendCoreWidgetsVisible();
    initConditionalScroll();
  });
})();
