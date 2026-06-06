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
  var LANGUAGE_CODES_NAME = "language_codes";
  var PRIMARY_LANGUAGE_FIELD = "primary_language_code";

  // In-flight fetch cache so rapid back-and-forth flips don't fire a
  // request per keystroke. Keyed by `code` or `code|lang`, value is a Promise.
  var inflight = Object.create(null);
  var memo = Object.create(null);
  var bootstrapCache = null;

  function readBootstrap() {
    if (bootstrapCache !== null) return bootstrapCache;
    bootstrapCache = {};
    var node = document.getElementById("page-data-rmc-signup-localization");
    if (!node) return bootstrapCache;
    try {
      bootstrapCache = JSON.parse(node.textContent || "{}") || {};
    } catch (_e) {
      bootstrapCache = {};
    }
    return bootstrapCache;
  }

  function resolveLocalizationUrl(code) {
    if (window.RMCPlatformSurface && window.RMCPlatformSurface.localizationUrl) {
      var fromSurface = window.RMCPlatformSurface.localizationUrl(code);
      if (fromSurface) return fromSurface;
    }
    var boot = readBootstrap();
    var pattern = boot.urls && boot.urls.localization_country;
    if (!pattern) return "";
    return String(pattern).replace(
      "{country_code}",
      encodeURIComponent(code || "")
    );
  }

  function init() {
    if (document.documentElement.dataset[INIT_FLAG] === "1") return;
    document.documentElement.dataset[INIT_FLAG] = "1";

    bindAllSelects();
    bindPrimaryLanguageButtons();
    syncSelectedCountry();
    document.body.addEventListener("htmx:afterSwap", function () {
      bindAllSelects();
      syncSelectedCountry();
    });
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
    applyCountryPack(code, "");
  }

  function syncSelectedCountry() {
    var code = currentCountryCode();
    if (!code || code.length !== 2) return;
    applyCountryPack(code, "");
  }

  function applyCountryPack(code, lang) {
    toggleIndiaStatePicker(code === "IN");
    fetchPack(code, lang).then(function (pack) {
      if (!pack) return;
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

  function indiaStateLanguageMap() {
    var boot = readBootstrap();
    return boot.india_state_language_map || {};
  }

  function primaryLanguageField() {
    return document.getElementById(PRIMARY_LANGUAGE_FIELD)
      || document.querySelector('input[name="' + PRIMARY_LANGUAGE_FIELD + '"]');
  }

  function selectedLanguageCodes(grid) {
    if (!grid) return [];
    var out = [];
    var checked = grid.querySelectorAll(
      'input[name="' + LANGUAGE_CODES_NAME + '"]:checked'
    );
    for (var i = 0; i < checked.length; i++) {
      var code = String(checked[i].value || "").toLowerCase();
      if (code && out.indexOf(code) < 0) out.push(code);
    }
    return out;
  }

  function resolveAutoPrimary(codes, pack) {
    if (!codes.length) return "";
    if (codes.length === 1) return codes[0];
    var cc = currentCountryCode();
    var picker = document.querySelector("[data-rmc-india-state-picker]");
    var state = picker && picker.value ? String(picker.value).trim().toUpperCase() : "";
    if (cc === "IN" && state) {
      var mapped = indiaStateLanguageMap()[state];
      if (mapped && codes.indexOf(mapped) >= 0) return mapped;
    }
    var defaultLang = String((pack && pack.language_code) || "").toLowerCase();
    if (defaultLang && codes.indexOf(defaultLang) >= 0) return defaultLang;
    var langs = (pack && pack.languages) || [];
    for (var i = 0; i < langs.length; i++) {
      if (!langs[i].is_default) continue;
      var dc = String(langs[i].code || "").toLowerCase();
      if (dc && codes.indexOf(dc) >= 0) return dc;
    }
    return codes[0];
  }

  function paintPrimaryLanguageBadges(grid, primaryCode) {
    if (!grid) return;
    var cards = grid.querySelectorAll("[data-rmc-language-code]");
    for (var i = 0; i < cards.length; i++) {
      var card = cards[i];
      var code = String(card.getAttribute("data-rmc-language-code") || "").toLowerCase();
      var input = card.querySelector('input[name="' + LANGUAGE_CODES_NAME + '"]');
      var isPrimary = code && code === primaryCode && input && input.checked;
      card.classList.toggle("rmc-signup-type-card--primary", !!isPrimary);
      var badge = card.querySelector("[data-rmc-language-primary-badge]");
      var starBtn = card.querySelector("[data-rmc-set-primary-language]");
      if (badge) badge.hidden = !isPrimary;
      if (starBtn) starBtn.hidden = !input || !input.checked || isPrimary;
    }
  }

  function setPrimaryLanguage(code, pack, grid) {
    var primary = String(code || "").toLowerCase();
    var field = primaryLanguageField();
    if (field) field.value = primary;
    paintPrimaryLanguageBadges(grid, primary);
    if (primary && pack) {
      fetchPrimaryLanguageOverlay(primary);
    }
  }

  function fetchPrimaryLanguageOverlay(lang) {
    var cc = currentCountryCode();
    if (!cc || !lang) return;
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
      renderTerminologyStrip(overlay.terminology || {});
    });
  }

  function syncPrimaryFromSelection(pack, grid) {
    var codes = selectedLanguageCodes(grid);
    if (!codes.length) {
      var langs = (pack && pack.languages) || [];
      if (langs[0]) codes = [String(langs[0].code || "").toLowerCase()];
    }
    var field = primaryLanguageField();
    var current = field ? String(field.value || "").toLowerCase() : "";
    var next = current && codes.indexOf(current) >= 0
      ? current
      : resolveAutoPrimary(codes, pack);
    setPrimaryLanguage(next, pack, grid);
  }

  function bindPrimaryLanguageButtons() {
    document.body.addEventListener("click", function (ev) {
      var btn = ev.target && ev.target.closest
        ? ev.target.closest("[data-rmc-set-primary-language]")
        : null;
      if (!btn) return;
      ev.preventDefault();
      var code = String(btn.getAttribute("data-rmc-set-primary-language") || "").toLowerCase();
      var grid = document.querySelector('[data-rmc-country-cards="' + CARD_KIND_LANGUAGE + '"]');
      setPrimaryLanguage(code, null, grid);
      fetchPrimaryLanguageOverlay(code);
    });
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
    var langGrid = document.querySelector('[data-rmc-country-cards="' + CARD_KIND_LANGUAGE + '"]');
    if (langGrid) {
      fetchPack(currentCountryCode(), "").then(function (pack) {
        syncPrimaryFromSelection(pack, langGrid);
      });
    }
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
    var url = resolveLocalizationUrl(code);
    if (!url) {
      var embedded = embeddedPackFor(code, lang);
      return embedded ? Promise.resolve(embedded) : Promise.resolve(null);
    }
    if (lang) url += (url.indexOf("?") >= 0 ? "&" : "?") + "lang=" + encodeURIComponent(lang);
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
        var fallback = embeddedPackFor(code, lang);
        if (fallback) {
          memo[key] = fallback;
          return fallback;
        }
        return null;
      });
    inflight[key] = p;
    return p;
  }

  function embeddedPackFor(code, lang) {
    var boot = readBootstrap();
    if (!boot.pack || String(boot.country_code || "").toUpperCase() !== code) {
      return null;
    }
    if (lang) return null;
    return boot.pack;
  }

  function renderTerminologyStrip(terminology) {
    var node = document.querySelector("[data-rmc-signup-terminology]");
    if (!node) return;
    var term = String((terminology && terminology.term) || "").trim();
    var grade = String((terminology && terminology.grade_level) || "").trim();
    var teacher = String((terminology && terminology.teacher) || "").trim();
    var parts = [];
    if (term) parts.push(term);
    if (grade) parts.push(grade);
    if (teacher) parts.push(teacher);
    if (!parts.length) {
      node.hidden = true;
      node.textContent = "";
      return;
    }
    node.hidden = false;
    node.textContent = "Local terms: " + parts.join(" · ");
  }

  function renderMigrationVendorHints(migration) {
    var select = document.getElementById("migration_vendor");
    var hint = document.querySelector("[data-rmc-migration-vendor-hint]");
    if (!migration || !select) return;
    if (hint && migration.hint) {
      hint.textContent = String(migration.hint);
    }
    var rec = migration.recommended_vendors;
    if (!rec || !rec.length) return;
    var current = select.value;
    var frag = document.createDocumentFragment();
    var blank = document.createElement("option");
    blank.value = "";
    blank.textContent = select.options[0] ? select.options[0].textContent : "No — starting fresh";
    frag.appendChild(blank);
    var seen = Object.create(null);
    for (var i = 0; i < rec.length; i++) {
      var slug = String(rec[i] || "").toLowerCase();
      if (!slug || seen[slug]) continue;
      seen[slug] = true;
      var opt = select.querySelector('option[value="' + cssEscape(slug) + '"]');
      if (!opt) continue;
      var clone = opt.cloneNode(true);
      if (i === 0 && clone.textContent.indexOf("★") !== 0) {
        clone.textContent = "★ " + clone.textContent;
      }
      frag.appendChild(clone);
    }
    for (var j = 0; j < select.options.length; j++) {
      var val = String(select.options[j].value || "").toLowerCase();
      if (!val || seen[val]) continue;
      frag.appendChild(select.options[j].cloneNode(true));
    }
    select.innerHTML = "";
    select.appendChild(frag);
    if (current) select.value = current;
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
    renderTerminologyStrip(pack.terminology || {});
    renderMigrationVendorHints(pack.migration || null);
  }

  function renderLanguageGrid(grid, languages, defaultLangCode) {
    var hostBlock = grid.closest("[data-rmc-language-block]");
    if (!languages || !languages.length) {
      if (hostBlock) hostBlock.hidden = true;
      grid.innerHTML = "";
      return;
    }
    if (hostBlock) hostBlock.hidden = languages.length < 2;
    var checkboxName =
      grid.getAttribute("data-rmc-country-cards-multi") || LANGUAGE_CODES_NAME;
    var isMulti = grid.getAttribute("data-rmc-multi-select") === "1";
    var selected = new Set();
    var checked = grid.querySelectorAll(
      'input[name="' + checkboxName + '"]:checked'
    );
    for (var i = 0; i < checked.length; i++) {
      selected.add(String(checked[i].value || "").toLowerCase());
    }
    if (!selected.size) {
      var fallback = String(defaultLangCode || "").toLowerCase();
      if (fallback) selected.add(fallback);
      else if (languages[0]) selected.add(String(languages[0].code || "").toLowerCase());
    }
    var field = primaryLanguageField();
    var primary = field ? String(field.value || "").toLowerCase() : "";
    if (!primary || !selected.has(primary)) {
      primary = resolveAutoPrimary(Array.from(selected), {
        language_code: defaultLangCode,
        languages: languages,
      });
    }
    var frag = document.createDocumentFragment();
    for (var j = 0; j < languages.length; j++) {
      frag.appendChild(
        buildLanguageCard(
          languages[j],
          checkboxName,
          selected,
          primary,
          isMulti
        )
      );
    }
    grid.innerHTML = "";
    grid.appendChild(frag);
    setPrimaryLanguage(primary, { language_code: defaultLangCode, languages: languages }, grid);
  }

  function buildLanguageCard(lang, inputName, selectedSet, primaryCode, isMulti) {
    var code = String(lang.code || "").toLowerCase();
    var native = String(lang.native_name || code);
    var region = String(lang.region || "");
    var hasOverlay = !!lang.has_education_system_overlay;
    var isSelected = selectedSet.has(code);
    var isPrimary = code === primaryCode && isSelected;
    var lbl = document.createElement("label");
    lbl.className =
      "rmc-signup-type-card" +
      (isSelected ? " rmc-signup-type-card--selected" : "") +
      (isPrimary ? " rmc-signup-type-card--primary" : "");
    lbl.setAttribute("data-rmc-language-code", code);
    var input = document.createElement("input");
    input.type = isMulti ? "checkbox" : "radio";
    input.name = inputName;
    input.value = code;
    input.className = "rmc-signup-type-card__input";
    if (isSelected) input.checked = true;
    input.addEventListener("change", onLanguageCheckboxChange);
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
    if (isPrimary) {
      var badge = document.createElement("span");
      badge.className = "rmc-signup-type-card__badge";
      badge.setAttribute("data-rmc-language-primary-badge", "1");
      badge.textContent = "\u2605 Primary";
      lbl.appendChild(badge);
    } else if (isMulti) {
      var star = document.createElement("button");
      star.type = "button";
      star.className = "rmc-signup-type-card__star btn btn-link btn-sm p-0";
      star.setAttribute("data-rmc-set-primary-language", code);
      star.textContent = "Set primary";
      star.hidden = !isSelected;
      lbl.appendChild(star);
    }
    if (hasOverlay) {
      var hint = document.createElement("span");
      hint.className = "rmc-signup-type-card__hint";
      hint.textContent = "Region-specific education system";
      lbl.appendChild(hint);
    }
    if (isMulti) {
      var check = document.createElement("span");
      check.className = "rmc-signup-type-card__check";
      check.setAttribute("aria-hidden", "true");
      check.textContent = "\u2713";
      lbl.appendChild(check);
    }
    return lbl;
  }

  function onLanguageCheckboxChange(ev) {
    onCardRadioChange(ev);
    var grid = ev.currentTarget && ev.currentTarget.closest
      ? ev.currentTarget.closest('[data-rmc-country-cards="' + CARD_KIND_LANGUAGE + '"]')
      : document.querySelector('[data-rmc-country-cards="' + CARD_KIND_LANGUAGE + '"]');
    var input = ev.currentTarget;
    if (input && input.type === "checkbox" && !input.checked) {
      var codes = selectedLanguageCodes(grid);
      if (!codes.length) {
        input.checked = true;
        return;
      }
    }
    var cc = currentCountryCode();
    if (!cc) return;
    fetchPack(cc, "").then(function (pack) {
      syncPrimaryFromSelection(pack, grid);
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
    var radioName =
      grid.getAttribute("data-rmc-country-cards-multi") ||
      grid.getAttribute("data-rmc-country-cards-radio") ||
      "school_type";
    var isMulti = grid.getAttribute("data-rmc-multi-select") === "1";
    var selected = new Set();
    if (isMulti) {
      var checked = grid.querySelectorAll(
        'input[name="' + radioName + '"]:checked'
      );
      for (var i = 0; i < checked.length; i++) {
        selected.add(String(checked[i].value || ""));
      }
    } else {
      var prev = grid.querySelector('input[name="' + radioName + '"]:checked');
      if (prev) selected.add(String(prev.value || ""));
    }
    var frag = document.createDocumentFragment();
    for (var j = 0; j < schoolTypes.length; j++) {
      frag.appendChild(
        buildSchoolTypeCard(schoolTypes[j], radioName, selected, isMulti)
      );
    }
    grid.innerHTML = "";
    grid.appendChild(frag);
  }

  function buildSchoolTypeCard(st, inputName, selectedSet, isMulti) {
    var code = String(st.code || "");
    var label = String(st.label || code);
    var glyph = String(st.glyph || "");
    var ages = String(st.typical_ages || "");
    var isSelected = selectedSet.has(code);
    var lbl = document.createElement("label");
    lbl.className =
      "rmc-signup-type-card" +
      (isSelected ? " rmc-signup-type-card--selected" : "");
    var input = document.createElement("input");
    input.type = isMulti ? "checkbox" : "radio";
    input.name = inputName;
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
    if (isMulti) {
      var check = document.createElement("span");
      check.className = "rmc-signup-type-card__check";
      check.setAttribute("aria-hidden", "true");
      check.textContent = "\u2713";
      lbl.appendChild(check);
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
    var isCheckbox = input.type === "checkbox";
    for (var i = 0; i < siblings.length; i++) {
      var lbl = siblings[i].closest(".rmc-calendar-card, .rmc-signup-type-card");
      if (!lbl) continue;
      var isCalendar = lbl.classList.contains("rmc-calendar-card");
      var addCls = isCalendar ? "rmc-calendar-card--selected" : "rmc-signup-type-card--selected";
      var rmCls1 = "rmc-calendar-card--selected";
      var rmCls2 = "rmc-signup-type-card--selected";
      if (isCheckbox) {
        if (siblings[i].checked) {
          lbl.classList.add(addCls);
        } else {
          lbl.classList.remove(rmCls1);
          lbl.classList.remove(rmCls2);
        }
        continue;
      }
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
