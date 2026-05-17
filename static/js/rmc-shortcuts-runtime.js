/**
 * Executes platform keyboard shortcuts (G-chords, /, page-specific actions).
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  var STORAGE_SINGLE = "rmc-kbd:single-char";
  var gPending = false;
  var gTimeout = null;
  var gbRowIndex = 0;

  function singleCharEnabled() {
    try {
      return localStorage.getItem(STORAGE_SINGLE) !== "0";
    } catch (_) {
      return true;
    }
  }

  function isTypingTarget(el) {
    if (!el) return false;
    var tag = (el.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return true;
    if (el.isContentEditable) return true;
    return false;
  }

  function readNav() {
    var node = document.getElementById("rmc-shortcuts-nav");
    if (!node || !node.textContent) return null;
    try {
      return JSON.parse(node.textContent);
    } catch (_) {
      return null;
    }
  }

  function getSurface() {
    if (window.RMCShortcuts && typeof window.RMCShortcuts.getSurface === "function") {
      return window.RMCShortcuts.getSurface();
    }
    return (document.documentElement.getAttribute("data-rmc-premium-shell") || "tenant").toLowerCase();
  }

  function getPage() {
    if (window.RMCShortcuts && typeof window.RMCShortcuts.getCurrentPage === "function") {
      return window.RMCShortcuts.getCurrentPage();
    }
    var el = document.querySelector("[data-rmc-page]");
    return el ? String(el.getAttribute("data-rmc-page") || "").toLowerCase() : "";
  }

  function focusSearch() {
    var el = document.querySelector(
      "[data-rmc-cmdk-input], #rmc-cmdk-input, input[type=search]:not([disabled]), .cp-topbar-search-input"
    );
    if (!el) return false;
    el.focus();
    if (typeof el.select === "function" && el.value) el.select();
    return true;
  }

  function goNav(key) {
    var nav = readNav();
    if (!nav || !nav[key]) return false;
    window.location.href = nav[key];
    return true;
  }

  function clickSelector(sel) {
    var el = document.querySelector(sel);
    if (!el) return false;
    el.click();
    return true;
  }

  function focusSelector(sel) {
    var el = document.querySelector(sel);
    if (!el) return false;
    el.focus();
    if (typeof el.select === "function" && el.value) el.select();
    return true;
  }

  function clickPagination(which) {
    var links = document.querySelectorAll(".pagination .page-link[href]");
    for (var i = 0; i < links.length; i++) {
      var text = (links[i].textContent || "").trim().toLowerCase();
      if (which === "next" && /next|›|»/i.test(text)) {
        links[i].click();
        return true;
      }
      if (which === "prev" && /prev|previous|‹|«/i.test(text)) {
        links[i].click();
        return true;
      }
    }
    return false;
  }

  function gradebookRows() {
    return Array.prototype.slice.call(
      document.querySelectorAll(".gradebook-table tbody tr input, .gradebook-table tbody tr select, .gradebook-table tbody tr textarea")
    );
  }

  function focusGradebookRow(delta) {
    var fields = gradebookRows();
    if (!fields.length) return false;
    gbRowIndex = (gbRowIndex + delta + fields.length) % fields.length;
    fields[gbRowIndex].focus();
    return true;
  }

  function handlePageShortcut(e) {
    var page = getPage();
    if (!singleCharEnabled()) return false;
    if (e.ctrlKey || e.metaKey || e.altKey) return false;

    if (page === "notifications-inbox") {
      if (e.key === "u" || e.key === "U") {
        if (clickSelector('a[href*="status=unread"]')) {
          e.preventDefault();
          return true;
        }
      }
      if (e.key === "a" || e.key === "A") {
        var all = document.querySelector('.rmc-table-density-toggle a[href*="user_notifications"]');
        if (all && !all.getAttribute("href").includes("status=")) {
          all.click();
          e.preventDefault();
          return true;
        }
        if (clickSelector('a[href*="user_notifications"]:not([href*="status="])')) {
          e.preventDefault();
          return true;
        }
      }
      if (e.key === "m" || e.key === "M") {
        var btn = document.querySelector('form[action*="mark_all_notifications_read"] button[type="submit"]');
        if (btn) {
          e.preventDefault();
          btn.click();
          return true;
        }
      }
      if (e.key === "o" || e.key === "O") {
        var link = document.querySelector(".rmc-inbox__item a[href]");
        if (link) {
          e.preventDefault();
          link.click();
          return true;
        }
      }
    }

    if (page === "teacher-gradebook") {
      if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
        var submit = document.querySelector('form button[type="submit"], form input[type="submit"]');
        if (submit) {
          e.preventDefault();
          submit.click();
          return true;
        }
      }
      if (e.key === "j" || e.key === "J") {
        if (focusGradebookRow(1)) {
          e.preventDefault();
          return true;
        }
      }
      if (e.key === "k" || e.key === "K") {
        if (focusGradebookRow(-1)) {
          e.preventDefault();
          return true;
        }
      }
    }

    if (page === "admissions-queue") {
      if (e.key === "f" || e.key === "F") {
        if (focusSelector("#applicant-q")) {
          e.preventDefault();
          return true;
        }
      }
      if (e.key === "a" || e.key === "A") {
        if (clickSelector('a[href*="backend_applicant_create"]')) {
          e.preventDefault();
          return true;
        }
      }
      if (e.key === "]") {
        if (clickPagination("next")) {
          e.preventDefault();
          return true;
        }
      }
      if (e.key === "[") {
        if (clickPagination("prev")) {
          e.preventDefault();
          return true;
        }
      }
    }

    if (page === "studio-os") {
      if (e.key === "f" || e.key === "F") {
        if (focusSelector("#studio-global-search")) {
          e.preventDefault();
          return true;
        }
      }
    }

    if (page === "finance-invoices") {
      if (e.key === "f" || e.key === "F") {
        if (focusSelector('#finance-invoices-filter-form input[name="q"]')) {
          e.preventDefault();
          return true;
        }
      }
      if (e.key === "o" || e.key === "O") {
        var inv = document.querySelector('table[aria-label*="Invoices"] tbody a[href*="invoices/"]');
        if (inv) {
          e.preventDefault();
          inv.click();
          return true;
        }
      }
    }
    return false;
  }

  document.addEventListener("keydown", function (e) {
    if (e.defaultPrevented) return;

    if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
      if (getPage() === "teacher-gradebook" && handlePageShortcut(e)) return;
    }

    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
      if (getPage() === "studio-os") {
        if (clickSelector("#studio-command-palette-btn")) {
          e.preventDefault();
          return;
        }
      }
    }

    if (handlePageShortcut(e)) return;

    if (e.ctrlKey || e.metaKey || e.altKey) {
      if (!(e.key === "s" || e.key === "S")) return;
    }

    if (e.key === "/" && !e.shiftKey) {
      if (isTypingTarget(e.target)) return;
      if (focusSearch()) e.preventDefault();
      return;
    }

    if (!singleCharEnabled()) return;

    var surface = getSurface();
    if (surface === "control-plane") return;

    if (e.key === "g" || e.key === "G") {
      if (isTypingTarget(e.target)) return;
      e.preventDefault();
      gPending = true;
      clearTimeout(gTimeout);
      gTimeout = setTimeout(function () {
        gPending = false;
      }, 1200);
      return;
    }

    if (!gPending || e.key.length !== 1) return;

    var k = e.key.toLowerCase();
    var handled = false;
    if (k === "h") handled = goNav("home");
    else if (k === "n") handled = goNav("notifications");
    else if (k === "c") handled = goNav("configure");

    if (handled) {
      e.preventDefault();
      gPending = false;
      clearTimeout(gTimeout);
    }
  });
})();
