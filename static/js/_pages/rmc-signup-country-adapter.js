/**
 * rmc-signup-country-adapter.js
 *
 * v3.62.2 (2026-05-22) — Wave 1 local-first push.
 *
 * Listens to the country dropdown on `/signup/` and `/super/schools/rapid/`.
 * When the user changes country, fetches `/api/v1/localization/<cc>/` and
 * re-renders TWO card grids in place:
 *
 *   1. `[data-rmc-country-cards="calendar"]` — calendar preset cards
 *   2. `[data-rmc-country-cards="school-type"]` — school-type cards
 *
 * Both grids carry `data-rmc-country-card-template` markup so the JS can
 * recreate them with country-local labels without coupling to a particular
 * grid library. Cards include the active radio behavior + selection class
 * that matches the server-rendered initial state.
 *
 * Pattern: CSP-safe IIFE, idempotent (`dataset.rmcSignupCountryAdapterInited`),
 * fail-soft (any fetch error leaves the existing cards untouched), HTMX-aware
 * (re-runs on `htmx:afterSwap`).
 */
(function () {
  "use strict";

  var INIT_FLAG = "rmcSignupCountryAdapterInited";
  var COUNTRY_SELECT_SELECTOR = "[data-rmc-signup-country], #country_code";
  var CARD_GRID_SELECTOR = "[data-rmc-country-cards]";
  var CARD_KIND_CALENDAR = "calendar";
  var CARD_KIND_SCHOOL_TYPE = "school-type";

  // In-flight fetch cache so rapid back-and-forth flips don't fire a
  // request per keystroke. Keyed by country code, value is a Promise.
  var inflight = Object.create(null);
  var memo = Object.create(null);

  function init() {
    if (document.documentElement.dataset[INIT_FLAG] === "1") return;
    document.documentElement.dataset[INIT_FLAG] = "1";

    bindAllSelects();
    document.body.addEventListener("htmx:afterSwap", bindAllSelects);
  }

  function bindAllSelects() {
    var nodes = document.querySelectorAll(COUNTRY_SELECT_SELECTOR);
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n.dataset.rmcCountryBound === "1") continue;
      n.dataset.rmcCountryBound = "1";
      n.addEventListener("change", onCountryChange);
    }
  }

  function onCountryChange(ev) {
    var sel = ev.currentTarget;
    var code = String((sel && sel.value) || "").trim().toUpperCase();
    if (!code || code.length !== 2) return;
    fetchPack(code).then(function (pack) {
      if (!pack) return;
      renderGrids(pack);
    });
  }

  function fetchPack(code) {
    if (memo[code]) return Promise.resolve(memo[code]);
    if (inflight[code]) return inflight[code];
    var url = "/api/v1/localization/" + encodeURIComponent(code) + "/";
    var p = fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        memo[code] = data;
        delete inflight[code];
        return data;
      })
      .catch(function () {
        delete inflight[code];
        return null;
      });
    inflight[code] = p;
    return p;
  }

  function renderGrids(pack) {
    var grids = document.querySelectorAll(CARD_GRID_SELECTOR);
    for (var i = 0; i < grids.length; i++) {
      var g = grids[i];
      var kind = (g.getAttribute("data-rmc-country-cards") || "").trim();
      if (kind === CARD_KIND_CALENDAR) {
        renderCalendarGrid(g, pack.calendar_systems || []);
      } else if (kind === CARD_KIND_SCHOOL_TYPE) {
        renderSchoolTypeGrid(g, pack.school_types || []);
      }
    }
  }

  function renderCalendarGrid(grid, calendarSystems) {
    if (!calendarSystems.length) return;
    var radioName = grid.getAttribute("data-rmc-country-cards-radio") || "term_preset";
    var prev = grid.querySelector("input[name=\"" + radioName + "\"]:checked");
    var prevValue = prev ? prev.value : "";
    var defaultValue = "";
    for (var i = 0; i < calendarSystems.length; i++) {
      if (calendarSystems[i].is_default) {
        defaultValue = String(calendarSystems[i].code || "");
        break;
      }
    }
    var preserve = "";
    for (var j = 0; j < calendarSystems.length; j++) {
      if (String(calendarSystems[j].code || "") === prevValue) {
        preserve = prevValue;
        break;
      }
    }
    var selected = preserve || defaultValue || String(calendarSystems[0].code || "");
    var frag = document.createDocumentFragment();
    for (var k = 0; k < calendarSystems.length; k++) {
      frag.appendChild(buildCalendarCard(calendarSystems[k], radioName, selected));
    }
    grid.innerHTML = "";
    grid.appendChild(frag);
  }

  function buildCalendarCard(cal, radioName, selectedCode) {
    var code = String(cal.code || "");
    var label = String(cal.label || code);
    var sub = String(cal.sub || "");
    var isSelected = code === selectedCode;
    var lbl = document.createElement("label");
    lbl.className = "rmc-calendar-card" + (isSelected ? " rmc-calendar-card--selected" : "");
    var input = document.createElement("input");
    input.type = "radio";
    input.name = radioName;
    input.value = code;
    input.className = "rmc-calendar-card__input";
    if (isSelected) input.checked = true;
    input.addEventListener("change", onCardRadioChange);
    var title = document.createElement("span");
    title.className = "rmc-calendar-card__title";
    title.textContent = label;
    var subSpan = document.createElement("span");
    subSpan.className = "rmc-calendar-card__sub";
    subSpan.textContent = sub;
    lbl.appendChild(input);
    lbl.appendChild(title);
    lbl.appendChild(subSpan);
    return lbl;
  }

  function renderSchoolTypeGrid(grid, schoolTypes) {
    if (!schoolTypes.length) return;
    var radioName = grid.getAttribute("data-rmc-country-cards-radio") || "school_type";
    var prev = grid.querySelector("input[name=\"" + radioName + "\"]:checked");
    var prevValue = prev ? prev.value : "";
    var preserve = "";
    for (var i = 0; i < schoolTypes.length; i++) {
      if (String(schoolTypes[i].code || "") === prevValue) {
        preserve = prevValue;
        break;
      }
    }
    var frag = document.createDocumentFragment();
    for (var j = 0; j < schoolTypes.length; j++) {
      frag.appendChild(buildSchoolTypeCard(schoolTypes[j], radioName, preserve));
    }
    grid.innerHTML = "";
    grid.appendChild(frag);
  }

  function buildSchoolTypeCard(st, radioName, selectedCode) {
    var code = String(st.code || "");
    var label = String(st.label || code);
    var glyph = String(st.glyph || "");
    var ages = String(st.typical_ages || "");
    var isSelected = code === selectedCode;
    var lbl = document.createElement("label");
    lbl.className =
      "rmc-signup-type-card" +
      (isSelected ? " rmc-signup-type-card--selected" : "");
    var input = document.createElement("input");
    input.type = "radio";
    input.name = radioName;
    input.value = code;
    input.className = "rmc-signup-type-card__input";
    if (isSelected) input.checked = true;
    input.addEventListener("change", onCardRadioChange);
    var glyphSpan = document.createElement("span");
    glyphSpan.className = "rmc-signup-type-card__glyph";
    glyphSpan.setAttribute("aria-hidden", "true");
    glyphSpan.textContent = glyph;
    var titleSpan = document.createElement("span");
    titleSpan.className = "rmc-signup-type-card__title";
    titleSpan.textContent = label;
    lbl.appendChild(input);
    lbl.appendChild(glyphSpan);
    lbl.appendChild(titleSpan);
    if (ages) {
      var sub = document.createElement("span");
      sub.className = "rmc-signup-type-card__sub";
      sub.textContent = ages;
      lbl.appendChild(sub);
    }
    return lbl;
  }

  // Toggle the --selected modifier when a card's radio is clicked, so the
  // user always sees which card is active without a page round-trip.
  function onCardRadioChange(ev) {
    var input = ev.currentTarget;
    if (!input || !input.name) return;
    var siblings = document.querySelectorAll(
      "input[name=\"" + input.name + "\"]"
    );
    for (var i = 0; i < siblings.length; i++) {
      var lbl = siblings[i].closest(".rmc-calendar-card, .rmc-signup-type-card");
      if (!lbl) continue;
      if (siblings[i] === input) {
        if (lbl.classList.contains("rmc-calendar-card")) {
          lbl.classList.add("rmc-calendar-card--selected");
        } else {
          lbl.classList.add("rmc-signup-type-card--selected");
        }
      } else {
        lbl.classList.remove("rmc-calendar-card--selected");
        lbl.classList.remove("rmc-signup-type-card--selected");
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
