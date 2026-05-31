/**
 * Platform-wide keyboard shortcut catalog (labelKey → rmc-shortcuts-i18n JSON).
 */
(function () {
  "use strict";
  if (typeof window === "undefined") return;

  window.RMCShortcuts = window.RMCShortcuts || {};
  var registry = [];
  var byId = {};
  var i18nCache = null;

  function readI18n() {
    if (i18nCache) return i18nCache;
    var node = document.getElementById("rmc-shortcuts-i18n");
    if (!node || !node.textContent) {
      i18nCache = {};
      return i18nCache;
    }
    try {
      i18nCache = JSON.parse(node.textContent);
    } catch (_) {
      i18nCache = {};
    }
    return i18nCache;
  }

  window.RMCShortcuts.t = function (key, fallback) {
    var map = readI18n();
    if (key && map[key]) return map[key];
    return fallback || key || "";
  };

  window.RMCShortcuts.resolveLabel = function (entry) {
    if (entry.labelKey) return window.RMCShortcuts.t(entry.labelKey, entry.label);
    return entry.label || "";
  };

  window.RMCShortcuts.resolveGroup = function (entry) {
    if (entry.groupKey) return window.RMCShortcuts.t(entry.groupKey, entry.group);
    return entry.group || "Help";
  };

  function add(entry) {
    if (!entry || !entry.id) return;
    if (!entry.labelKey && !entry.label) return;
    if (byId[entry.id]) return;
    byId[entry.id] = entry;
    registry.push(entry);
  }

  window.RMCShortcuts.register = function (entry) {
    if (!entry || !entry.keys) return;
    if (!entry.id) entry.id = "dyn-" + registry.length;
    if (!entry.labelKey && !entry.label) return;
    if (byId[entry.id]) {
      var idx = registry.findIndex(function (e) { return e.id === entry.id; });
      if (idx >= 0) registry[idx] = entry;
    } else {
      registry.push(entry);
    }
    byId[entry.id] = entry;
  };

  window.RMCShortcuts.all = function () {
    return registry.slice();
  };

  window.RMCShortcuts.getCurrentPage = function () {
    var el = document.querySelector("[data-rmc-page]");
    return el ? String(el.getAttribute("data-rmc-page") || "").toLowerCase() : "";
  };

  var CATALOG = [
    { id: "global-shortcuts", keys: ["?"], labelKey: "label.show_all", groupKey: "group.global", group: "Global", surfaces: ["*"] },
    { id: "global-f1", keys: ["F1"], labelKey: "label.show_all", groupKey: "group.global", group: "Global", surfaces: ["*"] },
    { id: "global-esc", keys: ["Esc"], labelKey: "label.close_dialog", groupKey: "group.global", group: "Global", surfaces: ["*"] },
    // v4.01.03 phantom-shortcut audit: `Ctrl+B` "Report problem" entry removed.
    // No keydown handler in `static/js/` actually listened for Ctrl+B and
    // dispatched the feedback trigger; the cheatsheet would advertise the
    // chord, AT users would press it, and nothing would happen. Re-add only
    // after wiring a real handler to `[data-rmc-feedback], [data-rmc-report-problem]`.
    {
      id: "search-cmdk",
      keys: ["Ctrl", "K"],
      labelKey: "label.open_cmdk",
      groupKey: "group.search",
      group: "Search",
      surfaces: ["portal", "tenant", "control-plane"],
      when: function () { return !!document.getElementById("rmc-cmdk"); },
      showUnavailable: true,
    },
    {
      id: "search-slash",
      keys: ["/"],
      labelKey: "label.focus_search",
      groupKey: "group.search",
      group: "Search",
      surfaces: ["*"],
      when: function () {
        return !!document.querySelector("[data-rmc-cmdk-input], #rmc-cmdk-input, input[type=search], .cp-topbar-search-input");
      },
      showUnavailable: true,
    },
    {
      id: "search-next",
      keys: ["J"],
      labelKey: "label.search_next",
      groupKey: "group.search",
      group: "Search",
      surfaces: ["portal", "tenant", "control-plane"],
      when: function () { return !!document.getElementById("rmc-cmdk"); },
      showUnavailable: true,
      singleChar: true,
    },
    {
      id: "search-prev",
      keys: ["K"],
      labelKey: "label.search_prev",
      groupKey: "group.search",
      group: "Search",
      surfaces: ["portal", "tenant", "control-plane"],
      when: function () { return !!document.getElementById("rmc-cmdk"); },
      showUnavailable: true,
      singleChar: true,
    },
    {
      id: "nav-g-h",
      keys: ["G", "H"],
      labelKey: "label.nav_home",
      groupKey: "group.navigation",
      group: "Navigation",
      surfaces: ["portal", "tenant"],
      showUnavailable: true,
      singleChar: true,
      when: function () {
        var n = document.getElementById("rmc-shortcuts-nav");
        return !!(n && n.textContent);
      },
    },
    {
      id: "nav-g-n",
      keys: ["G", "N"],
      labelKey: "label.nav_notifications",
      groupKey: "group.navigation",
      group: "Navigation",
      surfaces: ["portal", "tenant"],
      showUnavailable: true,
      singleChar: true,
      when: function () {
        var n = document.getElementById("rmc-shortcuts-nav");
        return !!(n && n.textContent);
      },
    },
    {
      id: "nav-g-c",
      keys: ["G", "C"],
      labelKey: "label.nav_profile",
      groupKey: "group.navigation",
      group: "Navigation",
      surfaces: ["portal", "tenant"],
      showUnavailable: true,
      singleChar: true,
      when: function () {
        var n = document.getElementById("rmc-shortcuts-nav");
        return !!(n && n.textContent);
      },
    },
    { id: "cp-g-d", keys: ["G", "D"], labelKey: "label.cp_dashboard", groupKey: "group.control_plane", group: "Control plane", surfaces: ["control-plane"], singleChar: true },
    { id: "cp-g-c", keys: ["G", "C"], labelKey: "label.cp_command_center", groupKey: "group.control_plane", group: "Control plane", surfaces: ["control-plane"], singleChar: true },
    { id: "cp-g-t", keys: ["G", "T"], labelKey: "label.cp_studio", groupKey: "group.control_plane", group: "Control plane", surfaces: ["control-plane"], singleChar: true },
    { id: "cp-g-o", keys: ["G", "O"], labelKey: "label.cp_orchestration", groupKey: "group.control_plane", group: "Control plane", surfaces: ["control-plane"], singleChar: true },
    { id: "cp-g-a", keys: ["G", "A"], labelKey: "label.cp_config", groupKey: "group.control_plane", group: "Control plane", surfaces: ["control-plane"], singleChar: true },
    { id: "cp-g-b", keys: ["G", "B"], labelKey: "label.cp_billing", groupKey: "group.control_plane", group: "Control plane", surfaces: ["control-plane"], singleChar: true },
    { id: "cp-g-s", keys: ["G", "S"], labelKey: "label.cp_support", groupKey: "group.control_plane", group: "Control plane", surfaces: ["control-plane"], singleChar: true },
    { id: "cp-g-m", keys: ["G", "M"], labelKey: "label.cp_migration", groupKey: "group.control_plane", group: "Control plane", surfaces: ["control-plane"], singleChar: true },
    { id: "cp-g-u", keys: ["G", "U"], labelKey: "label.cp_usage", groupKey: "group.control_plane", group: "Control plane", surfaces: ["control-plane"], singleChar: true },
    { id: "cp-g-health", keys: ["G", "H"], labelKey: "label.cp_health", groupKey: "group.control_plane", group: "Control plane", surfaces: ["control-plane"], singleChar: true },
    { id: "cp-g-p", keys: ["G", "P"], labelKey: "label.cp_pulse", groupKey: "group.control_plane", group: "Control plane", surfaces: ["control-plane"], singleChar: true },
    {
      id: "ai-copilot",
      keys: ["Ctrl", "Shift", "?"],
      labelKey: "label.ai_copilot",
      groupKey: "group.assistant",
      group: "Assistant",
      surfaces: ["portal", "tenant", "control-plane"],
      when: function () {
        return !!(document.querySelector("[data-ai-copilot-url], #ai-copilot-fab, .ai-copilot-trigger"));
      },
      showUnavailable: true,
    },
    // v4.01.03 phantom-shortcut audit: `Alt+T` and `T` theme-toggle entries
    // removed. `window.RMCTheme.toggle` does NOT exist as a globally bound
    // keydown handler — `rmc-theme-toggle.js` wires `click` listeners on
    // `[data-rmc-theme]` swatch buttons, never a keyboard chord. Marketing
    // `T` likewise has no `keydown` listener anywhere in `static/`. Re-add
    // only after wiring a real keydown handler in `rmc-theme-toggle.js`
    // (and a marketing equivalent) that calls `RMCTheme.set(...)`.
    {
      id: "inbox-unread",
      keys: ["U"],
      labelKey: "label.inbox_unread",
      groupKey: "group.inbox",
      group: "Inbox",
      pages: ["notifications-inbox"],
      singleChar: true,
      when: function () {
        return !!document.querySelector('a[href*="status=unread"]');
      },
      showUnavailable: true,
    },
    {
      id: "inbox-all",
      keys: ["A"],
      labelKey: "label.inbox_all",
      groupKey: "group.inbox",
      group: "Inbox",
      pages: ["notifications-inbox"],
      singleChar: true,
    },
    {
      id: "inbox-mark-read",
      keys: ["M"],
      labelKey: "label.inbox_mark_read",
      groupKey: "group.inbox",
      group: "Inbox",
      pages: ["notifications-inbox"],
      singleChar: true,
      when: function () {
        return !!document.querySelector('form[action*="mark_all_notifications_read"]');
      },
      showUnavailable: true,
    },
    {
      id: "inbox-open",
      keys: ["O"],
      labelKey: "label.inbox_open_first",
      groupKey: "group.inbox",
      group: "Inbox",
      pages: ["notifications-inbox"],
      singleChar: true,
      when: function () {
        return !!document.querySelector(".rmc-inbox__item a[href]");
      },
      showUnavailable: true,
    },
    {
      id: "gb-save",
      keys: ["Ctrl", "S"],
      labelKey: "label.gb_save",
      groupKey: "group.gradebook",
      group: "Gradebook",
      pages: ["teacher-gradebook"],
      when: function () {
        return !!document.querySelector('form button[type="submit"], form input[type="submit"]');
      },
      showUnavailable: true,
    },
    {
      id: "gb-next",
      keys: ["J"],
      labelKey: "label.gb_next_row",
      groupKey: "group.gradebook",
      group: "Gradebook",
      pages: ["teacher-gradebook"],
      singleChar: true,
      when: function () {
        return !!document.querySelector(".gradebook-table tbody tr");
      },
      showUnavailable: true,
    },
    {
      id: "gb-prev",
      keys: ["K"],
      labelKey: "label.gb_prev_row",
      groupKey: "group.gradebook",
      group: "Gradebook",
      pages: ["teacher-gradebook"],
      singleChar: true,
      when: function () {
        return !!document.querySelector(".gradebook-table tbody tr");
      },
      showUnavailable: true,
    },
    {
      id: "adm-focus-search",
      keys: ["F"],
      labelKey: "label.adm_focus_search",
      groupKey: "group.admissions",
      group: "Admissions",
      pages: ["admissions-queue"],
      singleChar: true,
      when: function () {
        return !!document.querySelector("#applicant-q");
      },
      showUnavailable: true,
    },
    {
      id: "adm-add",
      keys: ["A"],
      labelKey: "label.adm_add_applicant",
      groupKey: "group.admissions",
      group: "Admissions",
      pages: ["admissions-queue"],
      singleChar: true,
      when: function () {
        return !!document.querySelector('a[href*="backend_applicant_create"]');
      },
      showUnavailable: true,
    },
    {
      id: "adm-next-page",
      keys: ["]"],
      labelKey: "label.adm_next_page",
      groupKey: "group.admissions",
      group: "Admissions",
      pages: ["admissions-queue"],
      when: function () {
        return !!document.querySelector(".pagination .page-link[href*='page=']");
      },
      showUnavailable: true,
    },
    {
      id: "adm-prev-page",
      keys: ["["],
      labelKey: "label.adm_prev_page",
      groupKey: "group.admissions",
      group: "Admissions",
      pages: ["admissions-queue"],
      when: function () {
        return !!document.querySelector(".pagination .page-link[href*='page=']");
      },
      showUnavailable: true,
    },
    {
      id: "studio-focus-search",
      keys: ["F"],
      labelKey: "label.studio_focus_search",
      groupKey: "group.studio",
      group: "Studio OS",
      pages: ["studio-os"],
      singleChar: true,
      when: function () {
        return !!document.querySelector("#studio-global-search");
      },
      showUnavailable: true,
    },
    {
      id: "studio-commands",
      keys: ["Ctrl", "K"],
      labelKey: "label.studio_commands",
      groupKey: "group.studio",
      group: "Studio OS",
      pages: ["studio-os"],
      when: function () {
        return !!document.querySelector("#studio-command-palette-btn");
      },
      showUnavailable: true,
    },
    {
      id: "fin-focus-search",
      keys: ["F"],
      labelKey: "label.fin_focus_search",
      groupKey: "group.finance",
      group: "Finance",
      pages: ["finance-invoices"],
      singleChar: true,
      when: function () {
        return !!document.querySelector("#finance-invoices-filter-form input[name=q]");
      },
      showUnavailable: true,
    },
    {
      id: "fin-open-first",
      keys: ["O"],
      labelKey: "label.fin_open_first",
      groupKey: "group.finance",
      group: "Finance",
      pages: ["finance-invoices"],
      singleChar: true,
      when: function () {
        return !!document.querySelector('table[aria-label*="Invoices"] tbody a[href*="invoices/"]');
      },
      showUnavailable: true,
    },
    {
      id: "fin-filter-submit",
      keys: ["Enter"],
      labelKey: "label.fin_apply_filter",
      groupKey: "group.finance",
      group: "Finance",
      pages: ["finance-invoices"],
      when: function () {
        return !!document.querySelector("#finance-invoices-filter-form button[type=submit]");
      },
      showUnavailable: true,
    },
    { id: "help-shortcuts", keys: ["?"], labelKey: "label.open_panel", groupKey: "group.help", group: "Help", surfaces: ["*"] },
    { id: "help-esc", keys: ["Esc"], labelKey: "label.dismiss_help", groupKey: "group.help", group: "Help", surfaces: ["*"] },
  ];

  for (var i = 0; i < CATALOG.length; i++) {
    add(CATALOG[i]);
  }
})();
