/**
 * rmc-signup-country-adapter.js
 *
 * v3.62.8 (2026-05-22) — Wave 6 local-first push: per-language education systems.
 *
 * Listens to the country dropdown on `/signup/` and `/super/schools/rapid/`.
 * When the user changes country, fetches `/api/v1/localization/<cc>/` and
 * re-renders THREE pickers in place:
 *
 *   1. `[data-rmc-country-cards="language"]`     — official-language cards (NEW Wave 6)
 *   2. `[data-rmc-country-cards="calendar"]`     — calendar preset cards
 *   3. `[data-rmc-country-cards="school-type"]`  — school-type cards
 *
 * For multilingual countries (CM Anglo/Franco, CA EN/FR, BE NL/FR/DE, CH 4
 * languages, IN/PK/LK/SG/MY/PH/ZA, etc.) the language picker shows ALL
 * official languages with a "Recommended" badge on the default. Picking a
 * non-default language triggers a second fetch with `?lang=<bcp47>` that
 * returns the per-language education-system overlay — calendar + school
 * types + terminology + education levels switch to the per-region system
 * (CM-EN → British GCE O/A Level; CM-FR → French Baccalauréat; CA-FR →
 * Quebec CÉGEP; CH-DE → Schweizer Gymnasium / Matura; etc.).
 *
 * For monolingual countries the language picker shows a single read-only
 * row ("Language: English") and the calendar + school-type grids stay as-is.
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
  var CARD_KIND_LANGUAGE = "language";
  var CARD_KIND_CALENDAR = "calendar";
  var CARD_KIND_SCHOOL_TYPE = "school-type";
  var LANGUAGE_RADIO_DEFAULT = "language_code";

  // In-flight fetch cache so rapid back-and-forth flips don't fire a
  // request per keystroke. Keyed by `code` or `code|lang`, value is a Promise.
  var inflight = Object.create(null);
  var memo = Object.create(null);

  function init() {
    if (document.documentElement.dataset[INIT_FLAG] === "1") return;
    document.documentElement.dataset[INIT_FLAG] = "1";

    bindAllSelects();
    // Wave 14 — sync IN state picker visibility with pre-selected country.
    toggleIndiaStatePicker(currentCountryCode() === "IN");
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

  function currentCountryCode() {
    var sel = document.querySelector(COUNTRY_SELECT_SELECTOR);
    if (!sel || !sel.value) return "";
    return String(sel.value).trim().toUpperCase();
  }

  function onCountryChange(ev) {
    var sel = ev.currentTarget;
    var code = String((sel && sel.value) || "").trim().toUpperCase();
    if (!code || code.length !== 2) return;
    // Wave 14 — IN per-state mini-picker visibility tied to country pick.
    toggleIndiaStatePicker(code === "IN");
    fetchPack(code, "").then(function (pack) {
      if (!pack) return;
      // First emit: render language picker (uses baseline pack `languages`)
      // and calendar + school-type with baseline data. If a non-default
      // language is selected later, the language onChange refetches with
      // `?lang=` and overlays.
      renderGrids(pack);
    });
  }

  // Wave 14 (v3.62.19 — 2026-05-23) — IN per-state mini-picker.
  // Shows the "Which state?" select when India is the selected country,
  // hides it otherwise. When the operator picks a state, auto-flips the
  // calendar radio above to the right state-board variant via the existing
  // data-rmc-country-cards="calendar" grid.
  function toggleIndiaStatePicker(show) {
    var block = document.querySelector("[data-rmc-india-state-block]");
    if (!block) return;
    block.style.display = show ? "" : "none";
    var picker = document.querySelector("[data-rmc-india-state-picker]");
    if (!picker) return;
    if (!picker.dataset.rmcIndiaStateBound) {
      picker.dataset.rmcIndiaStateBound = "1";
      picker.addEventListener("change", onIndiaStateChange);
    }
    if (!show) {
      // Clear the picked state when leaving IN so a re-pick triggers fresh flip.
      picker.value = "";
    }
  }

  function onIndiaStateChange(ev) {
    var sel = ev.currentTarget;
    var opt = sel && sel.options[sel.selectedIndex];
    if (!opt) return;
    var calCode = opt.getAttribute("data-calendar-code") || "";
    if (!calCode) return;
    // Flip the calendar radio. The calendar grid carries
    // data-rmc-country-cards="calendar" + data-rmc-country-cards-radio="term_preset".
    var grid = document.querySelector('[data-rmc-country-cards="' + CARD_KIND_CALENDAR + '"]');
    if (!grid) return;
    var radio = grid.querySelector('input[type="radio"][value="' + cssEscape(calCode) + '"]');
    if (!radio) return;
    // Uncheck siblings + check this one + paint selected class.
    var siblings = grid.querySelectorAll('input[type="radio"][name="' + radio.name + '"]');
    for (var i = 0; i < siblings.length; i++) {
      siblings[i].checked = false;
      var card = siblings[i].closest(".rmc-calendar-card");
      if (card) card.classList.remove("rmc-calendar-card--selected");
    }
    radio.checked = true;
    var ownCard = radio.closest(".rmc-calendar-card");
    if (ownCard) ownCard.classList.add("rmc-calendar-card--selected");
    radio.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function cssEscape(v) {
    // Minimal CSS.escape polyfill for the values we ship (alphanumeric + hyphen).
    return String(v).replace(/[^a-zA-Z0-9_-]/g, function (ch) {
      return "\\" + ch;
    });
  }

  function fetchPack(code, lang) {
    var key = lang ? (code + "|" + lang) : code;
    if (memo[key]) return Promise.resolve(memo[key]);
    if (inflight[key]) return inflight[key];
    var url = "/api/v1/localization/" + encodeURIComponent(code) + "/";
    if (lang) url += "?lang=" + encodeURIComponent(lang);
    var p = fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        memo[key] = data;
        delete inflight[key];
        return data;
      })
      .catch(function () {
        delete inflight[key];
        return null;
      });
    inflight[key] = p;
    return p;
  }

  function renderGrids(pack) {
    var grids = document.querySelectorAll(CARD_GRID_SELECTOR);
    for (var i = 0; i < grids.length; i++) {
      var g = grids[i];
      var kind = (g.getAttribute("data-rmc-country-cards") || "").trim();
      if (kind === CARD_KIND_LANGUAGE) {
        renderLanguageGrid(g, pack.languages || [], pack.language_code || "");
      } else if (kind === CARD_KIND_CALENDAR) {
        renderCalendarGrid(g, pack.calendar_systems || []);
      } else if (kind === CARD_KIND_SCHOOL_TYPE) {
        renderSchoolTypeGrid(g, pack.school_types || []);
      }
    }
  }

  function renderLanguageGrid(grid, languages, defaultLangCode) {
    // No languages -> hide the picker block entirely (monolingual + missing).
    var hostBlock = grid.closest("[data-rmc-language-block]");
    if (!languages || !languages.length) {
      if (hostBlock) hostBlock.hidden = true;
      grid.innerHTML = "";
      return;
    }
    if (hostBlock) hostBlock.hidden = languages.length < 2;  // monolingual: hide picker; keep value implicit
    var radioName = grid.getAttribute("data-rmc-country-cards-radio") || LANGUAGE_RADIO_DEFAULT;
    // Preserve existing user pick when re-rendering for same country.
    var prev = grid.querySelector("input[name=\"" + radioName + "\"]:checked");
    var prevValue = prev ? prev.value : "";
    var selected = "";
    for (var i = 0; i < languages.length; i++) {
      var code = String(languages[i].code || "").toLowerCase();
      if (code === prevValue) { selected = code; break; }
    }
    if (!selected) selected = String(defaultLangCode || "").toLowerCase();
    if (!selected && languages[0]) selected = String(languages[0].code || "").toLowerCase();
    var frag = document.createDocumentFragment();
    for (var j = 0; j < languages.length; j++) {
      frag.appendChild(buildLanguageCard(languages[j], radioName, selected));
    }
    grid.innerHTML = "";
    grid.appendChild(frag);
    // If we just landed a non-default language as the preserved pick,
    // re-fetch the per-language overlay so calendar + school-type reflect it.
    if (selected && selected !== String(defaultLangCode || "").toLowerCase()) {
      var cc = currentCountryCode();
      if (cc) {
        fetchPack(cc, selected).then(function (overlay) {
          if (!overlay) return;
          var cgrids = document.querySelectorAll(CARD_GRID_SELECTOR);
          for (var k = 0; k < cgrids.length; k++) {
            var kind = (cgrids[k].getAttribute("data-rmc-country-cards") || "").trim();
            if (kind === CARD_KIND_CALENDAR) {
              renderCalendarGrid(cgrids[k], overlay.calendar_systems || []);
            } else if (kind === CARD_KIND_SCHOOL_TYPE) {
              renderSchoolTypeGrid(cgrids[k], overlay.school_types || []);
            }
          }
        });
      }
    }
  }

  function buildLanguageCard(lang, radioName, selectedCode) {
    var code = String(lang.code || "").toLowerCase();
    var native = String(lang.native_name || code);
    var region = String(lang.region || "");
    var isDefault = !!lang.is_default;
    var hasOverlay = !!lang.has_education_system_overlay;
    var isSelected = code === selectedCode;
    var lbl = document.createElement("label");
    lbl.className = "rmc-signup-type-card" + (isSelected ? " rmc-signup-type-card--selected" : "");
    var input = document.createElement("input");
    input.type = "radio";
    input.name = radioName;
    input.value = code;
    input.className = "rmc-signup-type-card__input";
    if (isSelected) input.checked = true;
    input.addEventListener("change", onLanguageRadioChange);
    var title = document.createElement("span");
    title.className = "rmc-signup-type-card__title";
    title.textContent = native;
    lbl.appendChild(input);
    lbl.appendChild(title);
    if (region) {
      var sub = document.createElement("span");
      sub.className = "rmc-signup-type-card__sub";
      sub.textContent = region;
      lbl.appendChild(sub);
    }
    if (isDefault) {
      var badge = document.createElement("span");
      badge.className = "rmc-signup-type-card__badge";
      badge.textContent = "Recommended";
      lbl.appendChild(badge);
    }
    if (hasOverlay) {
      var hint = document.createElement("span");
      hint.className = "rmc-signup-type-card__hint";
      hint.textContent = "Region-specific education system";
      lbl.appendChild(hint);
    }
    return lbl;
  }

  function onLanguageRadioChange(ev) {
    onCardRadioChange(ev);
    var input = ev.currentTarget;
    if (!input || !input.value) return;
    var lang = String(input.value).toLowerCase();
    var cc = currentCountryCode();
    if (!cc) return;
    fetchPack(cc, lang).then(function (overlay) {
      if (!overlay) return;
      var grids = document.querySelectorAll(CARD_GRID_SELECTOR);
      for (var i = 0; i < grids.length; i++) {
        var kind = (grids[i].getAttribute("data-rmc-country-cards") || "").trim();
        if (kind === CARD_KIND_CALENDAR) {
          renderCalendarGrid(grids[i], overlay.calendar_systems || []);
        } else if (kind === CARD_KIND_SCHOOL_TYPE) {
          renderSchoolTypeGrid(grids[i], overlay.school_types || []);
        }
      }
    });
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
      var isCalendar = lbl.classList.contains("rmc-calendar-card");
      var addCls = isCalendar ? "rmc-calendar-card--selected" : "rmc-signup-type-card--selected";
      var rmCls1 = "rmc-calendar-card--selected";
      var rmCls2 = "rmc-signup-type-card--selected";
      if (siblings[i] === input) {
        lbl.classList.add(addCls);
      } else {
        lbl.classList.remove(rmCls1);
        lbl.classList.remove(rmCls2);
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
