/* v4.00.12 — wizard search box on tenant_wizard_index.html
   Debounced query against /api/wizards/search/?q=&audience= ; renders top results.
   Pure DOM — no framework, no globals beyond document.querySelector. */

(function () {
  "use strict";

  var input = document.getElementById("rmc-wizard-search-input");
  var results = document.getElementById("rmc-wizard-search-results");
  var status = document.getElementById("rmc-wizard-search-status");
  if (!input || !results || !status) {
    return;
  }
  var endpoint = input.getAttribute("data-rmc-wizard-search-endpoint") || "";
  var audience = input.getAttribute("data-rmc-wizard-search-audience") || "";
  if (!endpoint) {
    return;
  }

  var debounceTimer = null;
  var lastQuery = "";
  var inFlightController = null;
  var RECENTS_KEY = "rmcWizardSearchRecent";
  var RECENTS_MAX = 5;

  function readRecents() {
    try {
      var raw = window.localStorage.getItem(RECENTS_KEY);
      if (!raw) return [];
      var parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed.filter(function(s){ return typeof s === "string"; });
      return [];
    } catch (e) { return []; }
  }

  function pushRecent(q) {
    if (!q) return;
    try {
      var current = readRecents();
      var deduped = [q].concat(current.filter(function(s){ return s !== q; }));
      window.localStorage.setItem(RECENTS_KEY, JSON.stringify(deduped.slice(0, RECENTS_MAX)));
    } catch (e) { /* localStorage may be disabled */ }
  }

  function renderRecents() {
    var holder = document.querySelector(".rmc-wizard-search");
    if (!holder) return;
    var existing = holder.querySelector(".rmc-wizard-search__recents");
    if (existing) existing.parentNode.removeChild(existing);
    var recents = readRecents();
    if (recents.length === 0) return;
    var wrap = document.createElement("div");
    wrap.className = "rmc-wizard-search__recents";
    wrap.setAttribute("aria-label", "Recent searches");
    for (var i = 0; i < recents.length; i++) {
      (function(q){
        var chip = document.createElement("button");
        chip.type = "button";
        chip.className = "rmc-wizard-search__recent-chip";
        chip.textContent = q;
        chip.addEventListener("click", function(){
          input.value = q;
          runQuery(q);
          input.focus();
        });
        wrap.appendChild(chip);
      })(recents[i]);
    }
    holder.insertBefore(wrap, results);
  }

  function clearResults() {
    while (results.firstChild) {
      results.removeChild(results.firstChild);
    }
    results.hidden = true;
  }

  function renderResults(payload) {
    clearResults();
    var items = (payload && payload.results) || [];
    if (items.length === 0) {
      status.textContent = "No wizards match that search.";
      return;
    }
    status.textContent = items.length + " match" + (items.length === 1 ? "" : "es") + ".";
    results.hidden = false;
    var max = items.length > 12 ? 12 : items.length;
    for (var i = 0; i < max; i++) {
      var entry = items[i];
      var li = document.createElement("li");
      li.className = "rmc-wizard-search__result-item";
      var a = document.createElement("a");
      a.className = "rmc-wizard-search__result";
      a.href = "/school/studio/wizards/" + encodeURIComponent(entry.wizard_key) + "/";
      var title = document.createElement("span");
      title.className = "rmc-wizard-search__result-title";
      // Prefer the server-humanized label; fall back gracefully. Never paints
      // a raw `wizards.*` slug (the label field is humanized server-side).
      title.textContent = entry.label || entry.label_token || entry.wizard_key;
      a.appendChild(title);
      var meta = document.createElement("span");
      meta.className = "rmc-wizard-search__result-meta";
      var aud = Array.isArray(entry.audience) ? entry.audience.join(", ") : "";
      meta.textContent = (entry.step_count || 0) + " steps - " + (entry.estimated_minutes || "?") + " min" + (aud ? " - " + aud : "");
      a.appendChild(meta);
      li.appendChild(a);
      results.appendChild(li);
    }
  }

  function runQuery(q) {
    if (q === lastQuery) {
      return;
    }
    lastQuery = q;
    if (!q) {
      clearResults();
      status.textContent = "";
      return;
    }
    if (inFlightController && typeof inFlightController.abort === "function") {
      try { inFlightController.abort(); } catch (e) { /* ignore */ }
    }
    var url = endpoint + "?q=" + encodeURIComponent(q);
    if (audience) {
      url += "&audience=" + encodeURIComponent(audience);
    }
    status.textContent = "Searching...";
    var supportsAbort = typeof window.AbortController !== "undefined";
    var opts = { credentials: "same-origin", headers: { "Accept": "application/json" } };
    if (supportsAbort) {
      inFlightController = new window.AbortController();
      opts.signal = inFlightController.signal;
    }
    fetch(url, opts).then(function (resp) {
      if (!resp.ok) {
        throw new Error("HTTP " + resp.status);
      }
      return resp.json();
    }).then(renderResults).catch(function (err) {
      if (err && err.name === "AbortError") {
        return;
      }
      status.textContent = "Search unavailable.";
      clearResults();
    });
  }

  input.addEventListener("input", function () {
    var raw = input.value || "";
    var q = raw.trim();
    if (debounceTimer !== null) {
      window.clearTimeout(debounceTimer);
    }
    debounceTimer = window.setTimeout(function () {
      runQuery(q);
    }, 200);
  });

  // v4.00.13: remember non-empty queries on Enter for recent-chip rendering.
  input.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") {
      var q = (input.value || "").trim();
      if (q) {
        pushRecent(q);
        renderRecents();
      }
    }
  });

  // v4.00.13: `/` outside any input focuses the wizard search box.
  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "/") return;
    var t = ev.target;
    if (!t) return;
    var tag = (t.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || t.isContentEditable) return;
    ev.preventDefault();
    input.focus();
  });

  // Initial render of recent chips on page load.
  renderRecents();
})();
