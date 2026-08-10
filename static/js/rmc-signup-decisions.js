/*
 * rmc-signup-decisions.js — progressive "recommended option" flags for signup.
 *
 * The setup step server-renders a decision model (recommended option pre-selected
 * and badged, country-auto-applied decisions flagged). As the operator changes an
 * UPSTREAM answer (country, school model, education cycles, campus count) this
 * refreshes those flags from /signup/decisions/ — the SAME deterministic engine
 * that produced the server render — so the "Recommended" badges never drift from
 * what will actually be provisioned.
 *
 * Progressive enhancement only: with no JS (or offline) the server-rendered flags
 * stand and the form submits exactly as before. A hand-picked select is never
 * overwritten; only its "Recommended" marker moves.
 */
(function () {
  "use strict";
  var form = document.querySelector("[data-rmc-signup-form]");
  var root = document.querySelector("[data-rmc-decisions]");
  if (!form || !root) return;
  var endpoint = root.getAttribute("data-rmc-decisions-endpoint");
  if (!endpoint) return;

  var RECO = root.getAttribute("data-rmc-reco-label") || "Recommended";
  var AUTO = root.getAttribute("data-rmc-auto-label") || "Auto";
  var touched = Object.create(null); // decision key -> operator hand-picked it

  function val(name) {
    var el = form.elements[name];
    return el ? String(el.value || "").trim() : "";
  }
  function cyclesCsv() {
    var out = [];
    var boxes = form.querySelectorAll('input[name="school_type"]:checked');
    Array.prototype.forEach.call(boxes, function (b) {
      if (b.value) out.push(b.value);
    });
    return out.join(",");
  }
  function cell(key) {
    return root.querySelector('[data-rmc-decision="' + key + '"]');
  }
  function recoSuffix(isReco) {
    return isReco ? " · " + RECO : "";
  }

  function applyDimension(dim) {
    var c = cell(dim.key);
    if (!c) return;
    c.hidden = false;
    var select = c.querySelector("[data-rmc-decision-select]");
    if (!select) return;
    select.disabled = false;

    var prev = touched[dim.key] ? select.value : "";
    var keepExists = false;
    select.setAttribute("data-rmc-recommended", dim.recommended_value);
    // Rebuild options — the option SET itself is country-dependent for some
    // decisions (e.g. the national exam board), so a full rebuild is simplest.
    select.innerHTML = "";
    (dim.options || []).forEach(function (o) {
      var opt = document.createElement("option");
      opt.value = o.value;
      opt.textContent = String(o.label) + recoSuffix(o.value === dim.recommended_value);
      select.appendChild(opt);
      if (o.value === prev) keepExists = true;
    });
    // Keep a hand-picked value if it still exists; otherwise take the reco.
    select.value = prev && keepExists ? prev : dim.recommended_value;

    var badge = c.querySelector("[data-rmc-decision-autobadge]");
    var note = c.querySelector("[data-rmc-decision-note]");
    if (!dim.ask) {
      if (!badge) {
        var lbl = c.querySelector("label");
        if (lbl) {
          badge = document.createElement("span");
          badge.className = "badge rounded-pill bg-info-subtle text-info-emphasis";
          badge.setAttribute("data-rmc-decision-autobadge", "1");
          badge.textContent = AUTO;
          lbl.appendChild(badge);
        }
      }
      if (note) note.textContent = String(dim.auto_reason || "");
    } else {
      if (badge && badge.parentNode) badge.parentNode.removeChild(badge);
      if (note) note.textContent = String(dim.help || "");
    }
  }

  function apply(model) {
    var present = Object.create(null);
    (model.dimensions || []).forEach(function (dim) {
      present[dim.key] = true;
      applyDimension(dim);
    });
    // A decision that no longer applies (e.g. session pattern for a higher-ed
    // only institution) is hidden AND disabled so it does not post a stale value.
    Array.prototype.forEach.call(
      root.querySelectorAll("[data-rmc-decision]"),
      function (c) {
        if (!present[c.getAttribute("data-rmc-decision")]) {
          c.hidden = true;
          var s = c.querySelector("[data-rmc-decision-select]");
          if (s) s.disabled = true;
        }
      }
    );
    // Nudge the "starting fit" panel (rmc-signup-balanced-v3.js) to recompute
    // from the values we just set. A form-level input event has target=form, so
    // it does not trip the per-select "touched" listener below.
    try {
      form.dispatchEvent(new Event("input", { bubbles: true }));
    } catch (e) {
      /* older browsers — the panel still refreshes on the next keystroke */
    }
  }

  var timer = null;
  var controller = null;
  function refresh() {
    if (!("fetch" in window)) return;
    var params = new URLSearchParams();
    params.set("country_code", val("country_code"));
    params.set("funding", val("funding_type"));
    params.set("cycles", cyclesCsv());
    params.set("campus_count", val("campus_count"));
    if (controller) {
      try { controller.abort(); } catch (e) { /* noop */ }
    }
    controller = "AbortController" in window ? new AbortController() : null;
    fetch(endpoint + "?" + params.toString(), {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
      signal: controller ? controller.signal : undefined,
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (model) { if (model && model.dimensions) apply(model); })
      .catch(function () { /* offline/aborted — keep the server-rendered flags */ });
  }
  function schedule() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(refresh, 250);
  }

  // The operator owns a decision the moment they change its select.
  root.addEventListener("change", function (e) {
    var s = e.target && e.target.closest
      ? e.target.closest("[data-rmc-decision-select]")
      : null;
    if (!s) return;
    var c = s.closest("[data-rmc-decision]");
    if (c) touched[c.getAttribute("data-rmc-decision")] = true;
  });

  // Recompute when an upstream answer changes. Country + cycle controls can be
  // re-rendered by the country adapter, so also listen at form level by name.
  ["country_code", "funding_type", "campus_count"].forEach(function (name) {
    var el = form.elements[name];
    if (el && el.addEventListener) el.addEventListener("change", schedule);
  });
  form.addEventListener("change", function (e) {
    var t = e.target;
    if (t && (t.name === "country_code" || t.name === "school_type" || t.name === "funding_type")) {
      schedule();
    }
  });
}());
