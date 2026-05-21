/* RMC Universal Command Bar (v3.53.0, 2026-05-21)
 *
 * Listens for cmd+k (macOS) / ctrl+k (Win/Linux) and toggles a luxury
 * palette overlay anywhere in the platform. Lazy-loads the action
 * registry from /api/command-bar/actions/ (Python-served, role +
 * tenant scoped).
 *
 * Armed-attribute pattern (per CLAUDE.md scan_reveal_armed_invariants):
 *   - sets data-rmc-command-bar-armed on <html> synchronously at parse
 *     time, BEFORE the IIFE that does the rest of init runs;
 *   - must be loaded WITHOUT defer/async so the armed flag lands
 *     before first paint and any CSS rule that gates on it activates
 *     before the user can see flicker.
 *
 * Tenant safety: the JSON endpoint server-filters actions by user +
 * school; this script does NO client-side role logic and trusts the
 * server. It also will never call any URL not present in the JSON
 * payload (no client-side URL synthesis).
 */
(function () {
  "use strict";

  // Armed flag must land at parse time (mirrors rmc-reveal.js pattern).
  try {
    if (document && document.documentElement) {
      document.documentElement.setAttribute("data-rmc-command-bar-armed", "1");
    }
  } catch (_e) {
    /* DOM not ready in some test harnesses — non-fatal. */
  }

  var ROOT_ID = "rmc-command-bar-root";
  var INPUT_ID = "rmc-command-bar-input";
  var LIST_ID = "rmc-command-bar-list";
  var EMPTY_ID = "rmc-command-bar-empty";
  var STATE = {
    actions: null,
    loading: false,
    loaded: false,
    open: false,
    filter: "",
    activeIndex: 0,
    actionsUrl: "",
  };

  function _qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function _allOptions() {
    var list = document.getElementById(LIST_ID);
    if (!list) return [];
    return Array.prototype.slice.call(
      list.querySelectorAll(".rmc-command-bar__option")
    );
  }

  function _filterActions(actions, q) {
    if (!q) return actions.slice();
    var needle = q.toLowerCase();
    return actions.filter(function (a) {
      var hay = (a.label + " " + (a.kind || "")).toLowerCase();
      return hay.indexOf(needle) !== -1;
    });
  }

  function _render() {
    var list = document.getElementById(LIST_ID);
    var empty = document.getElementById(EMPTY_ID);
    if (!list) return;
    var actions = STATE.actions || [];
    var filtered = _filterActions(actions, STATE.filter);
    list.innerHTML = "";
    if (filtered.length === 0) {
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;
    if (STATE.activeIndex >= filtered.length) {
      STATE.activeIndex = 0;
    }
    filtered.forEach(function (a, idx) {
      var li = document.createElement("li");
      li.setAttribute("role", "option");
      li.id = "rmc-cmd-bar-opt-" + idx;
      var btn = document.createElement("a");
      btn.href = a.url || "#";
      btn.className = "rmc-command-bar__option";
      btn.setAttribute("data-kind", a.kind || "navigate");
      if (idx === STATE.activeIndex) {
        btn.setAttribute("data-active", "true");
        btn.setAttribute("aria-selected", "true");
      } else {
        btn.setAttribute("aria-selected", "false");
      }
      var iconWrap = document.createElement("span");
      iconWrap.className = "rmc-command-bar__option-icon";
      iconWrap.setAttribute("aria-hidden", "true");
      iconWrap.textContent = a.icon || "›";
      var labelWrap = document.createElement("span");
      labelWrap.className = "rmc-command-bar__option-label";
      labelWrap.textContent = a.label || "";
      var kindWrap = document.createElement("span");
      kindWrap.className = "rmc-command-bar__option-kind";
      kindWrap.textContent = a.kind || "";
      btn.appendChild(iconWrap);
      btn.appendChild(labelWrap);
      btn.appendChild(kindWrap);
      li.appendChild(btn);
      list.appendChild(li);
    });
    var inputEl = document.getElementById(INPUT_ID);
    if (inputEl && filtered.length > 0) {
      inputEl.setAttribute(
        "aria-activedescendant",
        "rmc-cmd-bar-opt-" + STATE.activeIndex
      );
    }
  }

  function _loadActions(cb) {
    if (STATE.loaded || STATE.loading) {
      if (cb) cb();
      return;
    }
    if (!STATE.actionsUrl) {
      STATE.actions = [];
      STATE.loaded = true;
      if (cb) cb();
      return;
    }
    STATE.loading = true;
    try {
      var req = new XMLHttpRequest();
      req.open("GET", STATE.actionsUrl, true);
      req.setRequestHeader("Accept", "application/json");
      req.setRequestHeader("X-Requested-With", "XMLHttpRequest");
      req.onreadystatechange = function () {
        if (req.readyState !== 4) return;
        STATE.loading = false;
        STATE.loaded = true;
        var actions = [];
        if (req.status >= 200 && req.status < 300) {
          try {
            var payload = JSON.parse(req.responseText || "{}");
            if (payload && Array.isArray(payload.actions)) {
              actions = payload.actions;
            }
          } catch (_jsonErr) {
            actions = [];
          }
        }
        STATE.actions = actions;
        if (cb) cb();
      };
      req.send(null);
    } catch (_e) {
      STATE.loading = false;
      STATE.loaded = true;
      STATE.actions = [];
      if (cb) cb();
    }
  }

  // Debounce so search keystrokes don't re-render on every char.
  var _debounceTimer = null;
  function _onInput(ev) {
    var val = ev && ev.target ? String(ev.target.value || "") : "";
    if (_debounceTimer) {
      clearTimeout(_debounceTimer);
    }
    _debounceTimer = setTimeout(function () {
      STATE.filter = val;
      STATE.activeIndex = 0;
      _render();
    }, 80);
  }

  function _openBar() {
    if (STATE.open) return;
    var root = document.getElementById(ROOT_ID);
    if (!root) return;
    STATE.open = true;
    root.setAttribute("data-state", "open");
    root.setAttribute("aria-hidden", "false");
    _loadActions(function () {
      STATE.activeIndex = 0;
      _render();
      var input = document.getElementById(INPUT_ID);
      if (input) {
        try {
          input.focus();
        } catch (_e) {
          /* ignore focus errors in headless / hidden states */
        }
      }
    });
  }

  function _closeBar() {
    if (!STATE.open) return;
    var root = document.getElementById(ROOT_ID);
    if (!root) return;
    STATE.open = false;
    root.setAttribute("data-state", "closed");
    root.setAttribute("aria-hidden", "true");
    var input = document.getElementById(INPUT_ID);
    if (input) {
      input.value = "";
    }
    STATE.filter = "";
    STATE.activeIndex = 0;
  }

  function _toggleBar() {
    if (STATE.open) {
      _closeBar();
    } else {
      _openBar();
    }
  }

  function _activate(index) {
    var opts = _allOptions();
    if (index < 0) index = 0;
    if (index >= opts.length) index = opts.length - 1;
    STATE.activeIndex = index;
    opts.forEach(function (o, i) {
      if (i === index) {
        o.setAttribute("data-active", "true");
        o.setAttribute("aria-selected", "true");
        try {
          o.scrollIntoView({ block: "nearest" });
        } catch (_e) {
          /* ignore */
        }
      } else {
        o.removeAttribute("data-active");
        o.setAttribute("aria-selected", "false");
      }
    });
    var input = document.getElementById(INPUT_ID);
    if (input && opts.length > 0) {
      input.setAttribute(
        "aria-activedescendant",
        "rmc-cmd-bar-opt-" + index
      );
    }
  }

  function _confirmActive() {
    var opts = _allOptions();
    var node = opts[STATE.activeIndex];
    if (!node) return;
    var href = node.getAttribute("href");
    if (href && href !== "#") {
      window.location.href = href;
    }
  }

  function _onKeyDown(ev) {
    var isMac = navigator.platform && /Mac|iPod|iPhone|iPad/.test(navigator.platform);
    var modifier = isMac ? ev.metaKey : ev.ctrlKey;
    var key = ev.key ? ev.key.toLowerCase() : "";
    if (modifier && key === "k") {
      ev.preventDefault();
      _toggleBar();
      return;
    }
    if (!STATE.open) return;
    if (key === "escape") {
      ev.preventDefault();
      _closeBar();
      return;
    }
    if (key === "arrowdown") {
      ev.preventDefault();
      _activate(STATE.activeIndex + 1);
      return;
    }
    if (key === "arrowup") {
      ev.preventDefault();
      _activate(STATE.activeIndex - 1);
      return;
    }
    if (key === "enter") {
      ev.preventDefault();
      _confirmActive();
      return;
    }
  }

  function _onBackdropClick(ev) {
    var root = document.getElementById(ROOT_ID);
    if (!root) return;
    var panel = _qs(".rmc-command-bar__panel", root);
    if (!panel) return;
    if (ev.target && panel.contains(ev.target)) return;
    _closeBar();
  }

  function _init() {
    var root = document.getElementById(ROOT_ID);
    if (!root) return;
    STATE.actionsUrl = root.getAttribute("data-actions-url") || "";
    root.setAttribute("data-state", "closed");
    root.setAttribute("aria-hidden", "true");
    var input = document.getElementById(INPUT_ID);
    if (input) {
      input.addEventListener("input", _onInput);
    }
    root.addEventListener("click", _onBackdropClick);
    var list = document.getElementById(LIST_ID);
    if (list) {
      list.addEventListener("mouseover", function (ev) {
        var t = ev.target;
        while (t && t !== list) {
          if (t.classList && t.classList.contains("rmc-command-bar__option")) {
            var opts = _allOptions();
            var idx = opts.indexOf(t);
            if (idx !== -1) _activate(idx);
            break;
          }
          t = t.parentNode;
        }
      });
    }
    document.addEventListener("keydown", _onKeyDown);
    window.RMCCommandBar = {
      open: _openBar,
      close: _closeBar,
      toggle: _toggleBar,
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _init);
  } else {
    _init();
  }
})();
