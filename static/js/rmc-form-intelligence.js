/**
 * RunMyCampus Form Intelligence (v4.04.62) — platform-wide form elevation.
 *
 * One progressive-enhancement engine that auto-attaches to every real
 * <form method="post"> (with smart skips + a data-rmc-form-enhance="0" opt-out)
 * and ORCHESTRATES the form experience without duplicating the existing libs:
 *
 *   - Unsaved-changes guard + a sticky save bar (Discard / Save), for the
 *     forms that DON'T already carry the legacy [data-rmc-dirty-watch] markup
 *     (rmc-form-dirty.js keeps owning those).
 *   - Submit pending-state: spinner + lock + aria-busy on the submit control,
 *     released automatically if the submit was AJAX/validation-blocked. Kills
 *     double-submits. (Populates the aria-busy/data-loading-label hooks that
 *     already exist in the markup but were never driven.)
 *   - Live character counters from any maxlength field.
 *   - Blur-surfaced validation (.is-invalid) so errors show before submit —
 *     composes rmc-form-validation.js, which still owns the shake/scroll/focus
 *     on the native `invalid` event.
 *   - Section nav + scrollspy for long forms (>= 3 .form-section/fieldset).
 *
 * Config (default-on) comes from the #rmc-forms-config island (SITE cascade).
 * CSP-safe: createElement + textContent only, never innerHTML of runtime data.
 * Everything is wrapped in try/catch and no-ops when there are no forms.
 */
(function () {
  "use strict";

  var COUNTER_MIN = 24;        // only show a counter when maxlength is meaningful
  var COUNTER_WARN = 12;       // chars-remaining at which the counter turns amber
  var COUNTER_DANGER = 4;      // …and red
  var SECTION_MIN = 3;         // a "long form" worth a section nav
  var AJAX_RELEASE_MS = 0;     // microtask check of defaultPrevented
  var REGUARD_MS = 1200;       // re-arm the double-submit guard after an AJAX submit
  var WATCHDOG_MS = 8000;      // hard safety net: never leave a form locked forever
  var SPY_OFFSET = 140;        // scrollspy activation offset from the top
  var _secSeq = 0;             // module-wide counter for unique injected section ids

  var cfg = {
    intelligence: true,
    unsaved: true,
    pending: true,
    validation: true,
    section_nav: true,
  };

  function readConfig() {
    var node = document.getElementById("rmc-forms-config");
    if (!node || !node.textContent) { return; }
    try {
      var d = JSON.parse(node.textContent);
      Object.keys(cfg).forEach(function (k) {
        if (d[k] === false || d[k] === 0 || d[k] === "0") { cfg[k] = false; }
      });
    } catch (_) {}
  }

  /* ---------------- snapshot / dirty (mirrors rmc-form-dirty.js) ------------- */

  function snapshot(form) {
    var snap = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name) { return; }
      if (el.type === "checkbox" || el.type === "radio") {
        snap[el.name + ":" + (el.value || "")] = el.checked;
      } else {
        snap[el.name] = el.value;
      }
    });
    return snap;
  }
  function differs(a, b) {
    var k;
    for (k in a) { if (a[k] !== b[k]) { return true; } }
    for (k in b) { if (b[k] !== a[k]) { return true; } }
    return false;
  }

  /* ---------------- form qualification (auto-attach + smart skips) ---------- */

  function enhanceableControls(form) {
    return Array.prototype.filter.call(form.elements, function (el) {
      if (!el.name) { return false; }
      var t = (el.type || "").toLowerCase();
      return t !== "hidden" && t !== "submit" && t !== "button" && t !== "reset" && t !== "image";
    });
  }

  function shouldEnhance(form) {
    if (!form || form.dataset.rmcFormReady === "1") { return false; }
    if ((form.getAttribute("method") || "").toLowerCase() !== "post") { return false; }
    if (form.getAttribute("data-rmc-form-enhance") === "0") { return false; }
    if (form.hasAttribute("data-rmc-autosubmit")) { return false; }      // filter forms
    if ((form.getAttribute("role") || "") === "search") { return false; }
    // A real search form opts out — but ignore the table engine's injected
    // filter <input type=search> (it can land inside a form lacking a
    // .table-responsive wrapper); it carries a data-rmc-tbl-filter sentinel.
    if (form.querySelector('input[type="search"]:not([data-rmc-tbl-filter])')) { return false; }
    if (!enhanceableControls(form).length) { return false; }             // nothing to guard
    return true;
  }

  // Credential forms (login / password change) shouldn't sprout an "unsaved
  // changes" bar — but they still benefit from the submit pending-state.
  function isCredentialForm(form) {
    return !!form.querySelector('input[type="password"]');
  }

  /* ---------------- submit pending-state ------------------------------------ */

  function submitButtons(form) {
    return Array.prototype.slice.call(
      form.querySelectorAll('button[type="submit"], input[type="submit"], button:not([type])')
    );
  }

  function setBusy(form, busy, only) {
    // Lock ONLY the activated submitter when known (so multi-action forms — e.g.
    // Save vs Submit-for-review — don't dead-lock the other button); fall back to
    // all submit buttons when the submitter is unknown.
    var btns = only ? [only] : submitButtons(form);
    btns.forEach(function (btn) {
      if (!btn) { return; }
      if (busy) {
        if (btn.getAttribute("aria-busy") === "true") { return; }
        btn.setAttribute("aria-busy", "true");
        btn.classList.add("rmc-fi-busy");
        var loadingLabel = btn.getAttribute("data-loading-label");
        if (loadingLabel != null) {
          if (!btn.hasAttribute("data-rmc-fi-label")) { btn.setAttribute("data-rmc-fi-label", btn.textContent || ""); }
          if (btn.tagName === "BUTTON") { btn.textContent = loadingLabel; }
        }
      } else {
        btn.removeAttribute("aria-busy");
        btn.classList.remove("rmc-fi-busy");
        if (btn.hasAttribute("data-rmc-fi-label") && btn.tagName === "BUTTON") {
          btn.textContent = btn.getAttribute("data-rmc-fi-label");
          btn.removeAttribute("data-rmc-fi-label");
        }
      }
    });
  }

  function wirePending(form, onSubmitClean) {
    form.addEventListener("submit", function (e) {
      // Block a second submit while one is in flight.
      if (form.dataset.rmcSubmitting === "1") { e.preventDefault(); return; }
      // Invalid forms never reach here (the browser fires `invalid` instead),
      // but guard anyway so we never lock an unsubmittable form.
      if (form.checkValidity && !form.checkValidity()) { return; }

      var submitter = e.submitter || null;
      form.dataset.rmcSubmitting = "1";
      setBusy(form, true, submitter);
      if (typeof onSubmitClean === "function") { try { onSubmitClean(); } catch (_) {} }

      var unlocked = false;
      function unlock() {
        if (unlocked) { return; }
        unlocked = true;
        setBusy(form, false, submitter);
        form.dataset.rmcSubmitting = "0";
      }
      // Fast path: if a handler prevented navigation synchronously (AJAX/SPA),
      // release the visual lock now and re-arm the guard after a short window.
      setTimeout(function () {
        if (e.defaultPrevented) {
          setBusy(form, false, submitter);
          setTimeout(function () { if (!unlocked) { form.dataset.rmcSubmitting = "0"; } }, REGUARD_MS);
        }
        // Otherwise the page is navigating away; leave it locked (page unloads).
      }, AJAX_RELEASE_MS);
      // Hard safety net: covers AJAX that prevents default *asynchronously* (or
      // never navigates) — a real navigation unloads the page long before this.
      setTimeout(unlock, WATCHDOG_MS);
    }, false);
  }

  /* ---------------- unsaved guard + sticky save bar ------------------------- */

  var dirtyForms = (function () {
    var set = [];
    return {
      add: function (f) { if (set.indexOf(f) === -1) { set.push(f); } },
      remove: function (f) { var i = set.indexOf(f); if (i !== -1) { set.splice(i, 1); } },
      any: function () { return set.length > 0; },
    };
  })();

  function wireUnsaved(form) {
    var initial = snapshot(form);
    var dirty = false;

    var bar = document.createElement("div");
    bar.className = "rmc-fi-savebar";
    // A labelled region (not role=status) so the Save/Discard buttons aren't
    // announced as part of a live region; the message carries its own live role.
    bar.setAttribute("role", "region");
    bar.setAttribute("aria-label", "Unsaved changes");
    var dot = document.createElement("span"); dot.className = "rmc-fi-savebar__dot"; dot.setAttribute("aria-hidden", "true");
    var msg = document.createElement("span"); msg.className = "rmc-fi-savebar__msg"; msg.setAttribute("role", "status"); msg.setAttribute("aria-live", "polite"); msg.textContent = "Unsaved changes";
    var discard = document.createElement("button");
    discard.type = "button"; discard.className = "rmc-fi-savebar__btn"; discard.textContent = "Discard";
    var save = document.createElement("button");
    save.type = "button"; save.className = "rmc-fi-savebar__btn rmc-fi-savebar__btn--primary"; save.textContent = "Save changes";
    bar.appendChild(dot); bar.appendChild(msg); bar.appendChild(discard); bar.appendChild(save);
    form.appendChild(bar);

    function setDirty(next) {
      dirty = next;
      bar.classList.toggle("is-dirty", next);
      form.setAttribute("data-dirty", next ? "1" : "0");
      if (next) { dirtyForms.add(form); } else { dirtyForms.remove(form); }
    }
    function recheck() { setDirty(differs(initial, snapshot(form))); }

    // Re-baseline the snapshot the first time the user actually touches the form,
    // so programmatic field changes between load and first interaction (draft
    // restore, input masks, prefill) don't trigger a false "unsaved changes".
    var rebaselined = false;
    form.addEventListener("focusin", function () {
      if (!rebaselined && !dirty) { rebaselined = true; initial = snapshot(form); }
    });
    form.addEventListener("input", recheck);
    form.addEventListener("change", recheck);

    discard.addEventListener("click", function () {
      Array.prototype.forEach.call(form.elements, function (el) {
        if (!el.name) { return; }
        if (el.type === "checkbox" || el.type === "radio") {
          var key = el.name + ":" + (el.value || "");
          if (key in initial) { el.checked = initial[key]; }
        } else if (el.name in initial) {
          el.value = initial[el.name];
        }
      });
      // refresh any counters after a restore
      Array.prototype.forEach.call(form.querySelectorAll("[data-rmc-fi-counter]"), function (c) {
        var f = form.querySelector('[name="' + (window.CSS && CSS.escape ? CSS.escape(c.getAttribute("data-rmc-fi-counter")) : c.getAttribute("data-rmc-fi-counter")) + '"]');
        if (f) { updateCounter(f, c); }
      });
      setDirty(false);
    });

    save.addEventListener("click", function () {
      var btn = form.querySelector('button[type="submit"], input[type="submit"], button:not([type])');
      if (form.requestSubmit) { form.requestSubmit(btn && btn.type === "submit" ? btn : undefined); }
      else if (btn) { btn.click(); }
      else { form.submit(); }
    });

    return function onSubmitClean() { setDirty(false); };
  }

  /* ---------------- live character counters --------------------------------- */

  function updateCounter(field, counter) {
    var max = parseInt(field.getAttribute("maxlength"), 10);
    if (!max) { return; }
    var n = (field.value || "").length;
    var left = max - n;
    counter.textContent = n + " / " + max;
    counter.classList.toggle("is-warn", left <= COUNTER_WARN && left > COUNTER_DANGER);
    counter.classList.toggle("is-danger", left <= COUNTER_DANGER);
  }

  function wireCounters(form) {
    var fields = form.querySelectorAll("input[maxlength], textarea[maxlength]");
    Array.prototype.forEach.call(fields, function (field) {
      var max = parseInt(field.getAttribute("maxlength"), 10);
      if (!max || max < COUNTER_MIN) { return; }
      if (!field.name) { return; }
      var counter = document.createElement("div");
      counter.className = "rmc-fi-counter";
      counter.setAttribute("data-rmc-fi-counter", field.name);
      counter.setAttribute("aria-hidden", "true");
      if (field.parentNode) { field.parentNode.insertBefore(counter, field.nextSibling); }
      updateCounter(field, counter);
      field.addEventListener("input", function () { updateCounter(field, counter); });
    });
  }

  /* ---------------- blur-surfaced validation (composes the global lib) ------ */

  function wireBlurValidation(form) {
    Array.prototype.forEach.call(enhanceableControls(form), function (el) {
      if (!el.checkValidity) { return; }
      el.addEventListener("blur", function () {
        if (el.value === "" && !el.required) { return; }
        if (!el.checkValidity()) { el.classList.add("is-invalid"); }
      });
    });
  }

  /* ---------------- section nav + scrollspy (long forms) -------------------- */

  function sectionHeading(sec) {
    var h = sec.querySelector(".form-section__title, .rmc-form__legend, .rmc-form__section-title, legend, h2, h3");
    return h ? (h.textContent || "").trim() : "";
  }

  function wireSectionNav(form) {
    // Page-aware: the Django admin shell renders its own richer section
    // navigation (numbered fieldset headings + the labelled "On this page"
    // rail), so a generic top tab bar here would be a third, redundant copy of
    // the same list. Skip it inside the admin shell; keep it everywhere else.
    if (form.closest('[data-rmc-shell-root="django-admin"]')) { return; }

    var secs = Array.prototype.filter.call(
      form.querySelectorAll(".form-section, .rmc-form__section, fieldset"),
      function (s) { return sectionHeading(s); }
    );
    if (secs.length < SECTION_MIN) { return; }

    var nav = document.createElement("nav");
    nav.className = "rmc-fi-nav";
    nav.setAttribute("aria-label", "Form sections");
    var links = [];
    secs.forEach(function (sec, i) {
      if (!sec.id) { sec.id = "rmc-fi-sec-" + (_secSeq++); }
      var a = document.createElement("a");
      a.className = "rmc-fi-nav__link";
      a.href = "#" + sec.id;
      a.textContent = sectionHeading(sec);
      a.addEventListener("click", function (e) {
        e.preventDefault();
        try { sec.scrollIntoView({ behavior: "smooth", block: "start" }); } catch (_) { sec.scrollIntoView(); }
      });
      nav.appendChild(a);
      links.push(a);
    });
    form.insertBefore(nav, form.firstChild);

    function spy() {
      var top = window.scrollY + SPY_OFFSET;
      var cur = secs[0];
      secs.forEach(function (s) { if (s.offsetTop <= top) { cur = s; } });
      links.forEach(function (a) { a.classList.toggle("is-active", a.getAttribute("href") === "#" + cur.id); });
    }
    window.addEventListener("scroll", spy, { passive: true });
    spy();
  }

  /* ---------------- per-form orchestration ---------------------------------- */

  function enhance(form) {
    if (!shouldEnhance(form)) { return; }
    form.dataset.rmcFormReady = "1";

    var onSubmitClean = null;

    // Unsaved guard — only for forms NOT already owned by rmc-form-dirty.js,
    // and not for credential forms (a save bar there reads wrong).
    if (cfg.unsaved && !form.hasAttribute("data-rmc-dirty-watch") && !isCredentialForm(form)) {
      try { onSubmitClean = wireUnsaved(form); } catch (_) {}
    }
    if (cfg.validation) {
      try { wireCounters(form); } catch (_) {}
      try { wireBlurValidation(form); } catch (_) {}
    }
    if (cfg.section_nav) {
      try { wireSectionNav(form); } catch (_) {}
    }
    if (cfg.pending) {
      try { wirePending(form, onSubmitClean); } catch (_) {}
    }
  }

  function init() {
    readConfig();
    if (!cfg.intelligence) { return; }
    var forms = document.querySelectorAll("form");
    Array.prototype.forEach.call(forms, function (f) { try { enhance(f); } catch (_) {} });

    window.addEventListener("beforeunload", function (e) {
      if (dirtyForms.any()) { e.preventDefault(); e.returnValue = ""; return ""; }
    });

    window.RMCFormIntelligence = { enhance: enhance };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
