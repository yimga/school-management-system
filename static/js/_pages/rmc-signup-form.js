// rmc-signup-form.js — v3.57.x Wave 8 (2026-05-22)
//
// Live slug-availability check + auto-derive slug from school name on the
// public signup form (templates/schools/signup_school.html).
//
// CSP-safe: external script, no inline handlers, no eval, no new Function.
// Idempotent: re-running (e.g. after HTMX partial swap) is a no-op via the
// `data-rmc-signup-inited="1"` flag on the form element.
//
// DOM contract (provided by Agent A on the rewritten signup template):
//   <form data-rmc-signup-form>
//     <input id="name" data-rmc-signup-name>
//     <input id="slug" data-rmc-signup-slug>
//     <span id="signup-slug-pill" data-rmc-slug-pill aria-live="polite"></span>
//   </form>

(function () {
  'use strict';

  // Module-load gate — no-op on every other page.
  if (!document.querySelector('[data-rmc-signup-form]')) return;

  var DEBOUNCE_MS = 350;
  var SLUG_ENDPOINT = '/signup/slug-check/';

  function slugifyClient(value) {
    var s = (value || '').toString().toLowerCase().trim();
    s = s.replace(/[^a-z0-9]+/g, '-');
    s = s.replace(/^-+|-+$/g, '');
    return s.slice(0, 120);
  }

  function clearChildren(node) {
    while (node && node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function setPillState(pill, stateClass, text) {
    if (!pill) return;
    pill.className = 'rmc-slug-pill' + (stateClass ? ' ' + stateClass : '');
    clearChildren(pill);
    if (text) {
      pill.appendChild(document.createTextNode(text));
    }
  }

  function renderTakenPill(pill, slugInput, suggestions) {
    if (!pill) return;
    pill.className = 'rmc-slug-pill rmc-slug-pill--taken';
    clearChildren(pill);
    pill.appendChild(document.createTextNode('Taken.'));
    if (!suggestions || !suggestions.length) return;
    pill.appendChild(document.createTextNode(' Try: '));
    for (var i = 0; i < suggestions.length && i < 3; i++) {
      var s = suggestions[i];
      if (i > 0) {
        pill.appendChild(document.createTextNode(', '));
      }
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'rmc-slug-pill__suggestion';
      btn.appendChild(document.createTextNode(s));
      (function (chosen) {
        btn.addEventListener('click', function () {
          if (!slugInput) return;
          slugInput.value = chosen;
          // Treat picking a suggestion as a manual edit so auto-derive stops.
          slugInput.dataset.rmcUserTouched = '1';
          // Dispatch input so any other listeners (and our own debounce) react.
          var evt;
          try {
            evt = new Event('input', { bubbles: true });
          } catch (_e) {
            evt = document.createEvent('Event');
            evt.initEvent('input', true, true);
          }
          slugInput.dispatchEvent(evt);
          slugInput.focus();
        });
      })(s);
      pill.appendChild(btn);
    }
  }

  // v3.58.x Wave 9: country-picker → timezone / curriculum auto-suggest.
  // CSP-safe: no inline handlers; reads data-rmc-signup-country-tz and
  // data-rmc-signup-country-curriculum off the picked <option> and
  // populates the optional hidden inputs / radio cards. Idempotent —
  // we mark the select with data-rmc-signup-country-inited='1' so a
  // re-init (e.g. after HTMX partial swap) is a no-op.
  function initCountryAutoSuggest(form) {
    var countrySelect = form.querySelector('[data-rmc-signup-country]');
    if (!countrySelect) return;
    if (countrySelect.dataset.rmcSignupCountryInited === '1') return;
    countrySelect.dataset.rmcSignupCountryInited = '1';
    // Only run the auto-suggest path when the picker is a <select>; the
    // free-text fallback input also carries data-rmc-signup-country
    // but has no <option> children to read data-attrs from.
    if (countrySelect.tagName !== 'SELECT') return;

    function readPickedOption() {
      var idx = countrySelect.selectedIndex;
      if (idx < 0) return null;
      var opt = countrySelect.options[idx];
      if (!opt) return null;
      return {
        tz: opt.getAttribute('data-rmc-signup-country-tz') || '',
        curriculum:
          opt.getAttribute('data-rmc-signup-country-curriculum') || '',
        code: opt.value || ''
      };
    }

    function applyCountryHints() {
      var pick = readPickedOption();
      if (!pick) return;

      // Surface the timezone via a hidden input the form already carries
      // (or create one on first pick so it submits with POST). Operators
      // who land on the form via a deep link with ?country_code=KE see
      // this populated on initial render.
      if (pick.tz) {
        var tzInput = form.querySelector('input[name="timezone"]');
        if (!tzInput) {
          tzInput = document.createElement('input');
          tzInput.type = 'hidden';
          tzInput.name = 'timezone';
          tzInput.setAttribute('data-rmc-signup-country-tz-input', '1');
          form.appendChild(tzInput);
        }
        // Only auto-fill if the user hasn't manually edited timezone.
        if (tzInput.dataset.rmcUserTouched !== '1') {
          tzInput.value = pick.tz;
        }
      }

      // Curriculum hint maps to the term_preset radios. We only flip
      // UK ↔ default; anything else leaves the operator's choice alone.
      // The radios are rendered by Django when
      // cockpit.signup_form.show_calendar_cards is True.
      if (pick.curriculum) {
        var hint = pick.curriculum.toLowerCase();
        var target = '';
        if (hint.indexOf('uk') !== -1 || hint.indexOf('british') !== -1) {
          target = 'UK';
        }
        if (target) {
          var radios = form.querySelectorAll('input[name="term_preset"]');
          for (var i = 0; i < radios.length; i++) {
            if (radios[i].dataset.rmcUserTouched === '1') return;
            if (radios[i].value === target) {
              radios[i].checked = true;
            }
          }
        }
      }
    }

    countrySelect.addEventListener('change', applyCountryHints);

    // Mark radios as user-touched once the operator manually flips one
    // so a later country change doesn't overwrite their explicit choice.
    var calendarRadios = form.querySelectorAll('input[name="term_preset"]');
    for (var j = 0; j < calendarRadios.length; j++) {
      calendarRadios[j].addEventListener('change', function (ev) {
        ev.target.dataset.rmcUserTouched = '1';
      });
    }

    // Fire once on init in case the page loaded with a country preselected.
    applyCountryHints();
  }

  function initForm(form) {
    if (form.dataset.rmcSignupInited === '1') return;
    form.dataset.rmcSignupInited = '1';

    // v3.58.x Wave 9: wire the country picker first so any
    // server-side preselection populates the timezone hidden input
    // before the user starts editing other fields.
    initCountryAutoSuggest(form);

    var nameInput = form.querySelector('[data-rmc-signup-name]')
      || document.getElementById('name');
    var slugInput = form.querySelector('[data-rmc-signup-slug]')
      || document.getElementById('slug');
    var pill = form.querySelector('[data-rmc-slug-pill]')
      || document.getElementById('signup-slug-pill');

    if (!slugInput || !pill) return;

    var debounceHandle = null;
    var inflight = null;
    // Track whether the user has manually edited the slug input. We do NOT
    // overwrite their typed value with an auto-derived one.
    if (typeof slugInput.dataset.rmcUserTouched === 'undefined') {
      slugInput.dataset.rmcUserTouched = '';
    }

    function userTouched() {
      return slugInput.dataset.rmcUserTouched === '1';
    }

    function checkSlug(rawSlug) {
      var normalized = slugifyClient(rawSlug);
      if (!normalized) {
        setPillState(pill, '', '');
        return;
      }

      if (inflight) {
        try { inflight.abort(); } catch (_e) { /* ignore */ }
        inflight = null;
      }

      setPillState(pill, 'rmc-slug-pill--checking', 'Checking…');

      var controller = null;
      try {
        controller = new AbortController();
      } catch (_e) {
        controller = null;
      }
      inflight = controller;

      var url = SLUG_ENDPOINT + '?slug=' + encodeURIComponent(normalized);
      // Pass country_code through if the form carries one (hidden input).
      var ccInput = form.querySelector('input[name="country_code"]');
      if (ccInput && ccInput.value) {
        url += '&country_code=' + encodeURIComponent(ccInput.value);
      }

      var opts = { credentials: 'same-origin' };
      if (controller) opts.signal = controller.signal;

      fetch(url, opts)
        .then(function (resp) {
          if (!resp.ok) {
            throw new Error('bad-status');
          }
          return resp.json();
        })
        .then(function (data) {
          if (!data || typeof data !== 'object') {
            setPillState(pill, '', '');
            return;
          }
          if (data.available === true) {
            setPillState(pill, 'rmc-slug-pill--available', '✓ Available');
            return;
          }
          if (data.reason === 'taken') {
            renderTakenPill(pill, slugInput, data.suggestions || []);
            return;
          }
          if (data.reason === 'invalid') {
            setPillState(pill, 'rmc-slug-pill--invalid', 'Invalid URL');
            return;
          }
          setPillState(pill, '', '');
        })
        .catch(function (_err) {
          // Silent on abort or network error — never break the form.
          setPillState(pill, '', '');
        });
    }

    function scheduleCheck(rawSlug) {
      if (debounceHandle) {
        clearTimeout(debounceHandle);
        debounceHandle = null;
      }
      debounceHandle = setTimeout(function () {
        debounceHandle = null;
        checkSlug(rawSlug);
      }, DEBOUNCE_MS);
    }

    if (nameInput) {
      nameInput.addEventListener('input', function () {
        if (userTouched()) return;
        var derived = slugifyClient(nameInput.value);
        slugInput.value = derived;
        scheduleCheck(derived);
      });
    }

    slugInput.addEventListener('input', function () {
      // Mark touched so auto-derive stops shadowing the operator's edits.
      slugInput.dataset.rmcUserTouched = '1';
      scheduleCheck(slugInput.value);
    });

    // Initial state on page load: if the slug input already carries a value
    // (server-side prefill, e.g. ?slug=foo), fire one check immediately so
    // the operator sees availability without typing.
    var initialSlug = (slugInput.value || '').trim();
    if (initialSlug && !userTouched()) {
      checkSlug(initialSlug);
    }
  }

  function initAll() {
    var forms = document.querySelectorAll('[data-rmc-signup-form]');
    for (var i = 0; i < forms.length; i++) {
      initForm(forms[i]);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})();
