/**
 * rmc-command-palette-page-aware.js — v4.00.34 (2026-05-29)
 *
 * v4.00.34: + Voice elapsed-ms pulse: the mic button shows a tiny live
 *             "0.4s" counter while dictating, so the user can tell whether
 *             the recognizer is still listening (often hard on noisy mics).
 *
 * v4.00.31: + Locale-aware voice input: rec.lang now reads from the cmdk
 *             data block's `locale` (Django LANGUAGE_CODE) before falling
 *             back to navigator.language — so a Francophone tenant gets
 *             French dictation, not en-US.
 *           + Opt-in LLM fallback: when the deterministic pattern misses
 *             AND the input ends with " ??" or a long (>20 char) query,
 *             re-fetch with &ai=1 — escalates to the gateway for a
 *             single round-trip. Keeps default latency tight.
 * v4.00.30: + Web Speech API voice input on the cmdk input bar.
 *           + AI-line interpreter: as the user types, debounce-POST the
 *             query to /api/v1/ai/line-interpret/. When the backend matches
 *             a deterministic intent (e.g. "students who haven't paid term
 *             2" → outstanding fees), prepend a single AI suggestion row
 *             with the resolved URL — one-click jump instead of scrolling
 *             through generic results.
 *
 * Augmentation layer that runs BEFORE rmc-command-palette.js. It reads
 * data-rmc-page-domain on <html> (set by admin-quickaction.js's page
 * personality auto-detector) and prepends a "Page actions" group to the
 * command palette JSON data block — so when the user hits ⌘K from a
 * Finance page, the palette opens with Finance-specific quick actions
 * at the top: "New invoice", "Outstanding balances", "Payment runs",
 * etc. From a People page, it's "Add student", "Bulk import roster",
 * "Send broadcast", etc.
 *
 * The augmentation is INSERT-ONLY: it does not modify or remove any
 * existing palette items. Honors the OS-grade aesthetic via
 * data-rmc-cmdk-group="page" so the OS-grade CSS can wash the section
 * with an accent stripe.
 */
(function () {
  "use strict";

  var DATA_ID = "rmc-cmdk-data";

  /* Map data-rmc-page-domain -> array of {label, url|action, icon, keywords}.
     Keep each domain's list tight (5-7 items) so the palette stays scannable.
     URLs are best-effort; if a route is not present in this deploy, the
     palette skips it via its url-or-action validation. */
  var DOMAIN_ACTIONS = {
    finance: [
      { label: "New invoice",        url: "/finance/invoices/new/",         icon: "bi-receipt",           keywords: "fee bill charge" },
      { label: "Outstanding balances", url: "/finance/outstanding/",        icon: "bi-cash-coin",         keywords: "owed receivables overdue" },
      { label: "Payment runs",       url: "/finance/payments/",             icon: "bi-bank",              keywords: "transactions ledger" },
      { label: "Fee schedules",      url: "/finance/fee-schedules/",        icon: "bi-calendar3",         keywords: "tuition pricing" },
      { label: "Payroll dashboard",  url: "/payroll/",                      icon: "bi-wallet2",           keywords: "salaries staff payroll" }
    ],
    people: [
      { label: "Add student",        url: "/people/students/new/",          icon: "bi-person-plus",       keywords: "enroll register" },
      { label: "Bulk import roster", url: "/people/students/import/",       icon: "bi-cloud-upload",      keywords: "csv excel upload" },
      { label: "Send broadcast",     url: "/communication/broadcast/new/",  icon: "bi-megaphone",         keywords: "announce message email sms" },
      { label: "Staff directory",    url: "/people/staff/",                 icon: "bi-people",            keywords: "teacher staff" },
      { label: "Parent / guardian list", url: "/people/parents/",           icon: "bi-person-hearts",     keywords: "guardian family" }
    ],
    academic: [
      { label: "Open gradebook",     url: "/evals/teacher/dashboard/",      icon: "bi-table",             keywords: "grades marks" },
      { label: "Curriculum map",     url: "/curriculum/",                   icon: "bi-diagram-3",         keywords: "subjects scope sequence" },
      { label: "New assessment",     url: "/evals/assessments/new/",        icon: "bi-clipboard-check",   keywords: "quiz test exam" },
      { label: "Bulk grade entry",   url: "/evals/teacher/marks/bulk/",     icon: "bi-pencil-square",     keywords: "marks entry" },
      { label: "Class ranking",      url: "/evals/school-ranking/",         icon: "bi-trophy",            keywords: "top performers ranking" }
    ],
    operations: [
      { label: "Mark attendance",    url: "/attendance/take/",              icon: "bi-check2-square",     keywords: "register absent present" },
      { label: "Today's timetable",  url: "/timetable/today/",              icon: "bi-calendar-week",     keywords: "schedule classes periods" },
      { label: "Calendar",           url: "/calendar/",                     icon: "bi-calendar3",         keywords: "events terms" },
      { label: "Substitute teacher", url: "/timetable/substitutes/",        icon: "bi-arrow-repeat",      keywords: "cover sub replacement" },
      { label: "Bell schedule",      url: "/timetable/bells/",              icon: "bi-bell",              keywords: "periods bell ring" }
    ],
    admissions: [
      { label: "New application",    url: "/admissions/applications/new/",  icon: "bi-file-earmark-plus", keywords: "applicant intake" },
      { label: "Lead inbox",         url: "/admissions/leads/",             icon: "bi-inbox",             keywords: "prospects funnel" },
      { label: "Application queue",  url: "/admissions/queue/",             icon: "bi-stack",             keywords: "review status" },
      { label: "Offer letters",      url: "/admissions/offers/",            icon: "bi-envelope-paper",    keywords: "acceptance offer" }
    ],
    comms: [
      { label: "New broadcast",      url: "/communication/broadcast/new/",  icon: "bi-megaphone",         keywords: "announcement email sms" },
      { label: "Inbox (messages)",   url: "/accounts/messages/",            icon: "bi-chat-square-text",  keywords: "dm conversation" },
      { label: "Notifications inbox", url: "/accounts/notifications/",      icon: "bi-bell",              keywords: "alerts" },
      { label: "Templates",          url: "/communication/templates/",      icon: "bi-file-text",         keywords: "snippet boilerplate" }
    ],
    fleet: [
      { label: "Route monitor",      url: "/transport/routes/",             icon: "bi-geo-alt",           keywords: "bus route gps" },
      { label: "Vehicle roster",     url: "/transport/vehicles/",           icon: "bi-truck",             keywords: "fleet vehicles" },
      { label: "Driver schedule",    url: "/transport/drivers/",            icon: "bi-person-badge",      keywords: "driver schedule" }
    ],
    hostel: [
      { label: "Hostel occupancy",   url: "/hostel/occupancy/",             icon: "bi-house-door",        keywords: "rooms beds" },
      { label: "Boarding roster",    url: "/hostel/roster/",                icon: "bi-people-fill",       keywords: "boarders" },
      { label: "Meal plans",         url: "/hostel/meal-plans/",            icon: "bi-cup-hot",           keywords: "cafeteria food" }
    ],
    marketplace: [
      { label: "Browse marketplace", url: "/marketplace/",                  icon: "bi-shop",              keywords: "apps integrations" },
      { label: "Installed apps",     url: "/marketplace/installed/",        icon: "bi-grid-3x3",          keywords: "installed addons" },
      { label: "Connector status",   url: "/marketplace/connectors/",       icon: "bi-plug",              keywords: "integration webhooks" }
    ],
    security: [
      { label: "Security posture",   url: "/accounts/security/",            icon: "bi-shield-check",      keywords: "mfa posture score" },
      { label: "Audit log",          url: "/compliance/audit/",             icon: "bi-journal-text",      keywords: "logs trail" },
      { label: "Access control",     url: "/access/",                       icon: "bi-key",               keywords: "permissions rbac" }
    ],
    admin: [
      { label: "Tenants",            url: "/admin/tenancy/",                icon: "bi-buildings",         keywords: "schools tenants" },
      { label: "Site settings",      url: "/admin/siteconfig/sitesettings/", icon: "bi-sliders",          keywords: "config" },
      { label: "Operator team",      url: "/admin/accounts/",               icon: "bi-people-gear",       keywords: "admin users" }
    ]
  };

  function getDomain() {
    var d = document.documentElement.getAttribute("data-rmc-page-domain");
    if (d) return d;
    var m = document.querySelector('meta[name="rmc-page-domain"]');
    return (m && m.content) ? m.content : "";
  }

  function injectPageActions() {
    var node = document.getElementById(DATA_ID);
    if (!node || !node.textContent) return;
    var data;
    try { data = JSON.parse(node.textContent); } catch (e) { return; }
    if (!data || !Array.isArray(data.groups)) return;

    var domain = getDomain();
    var items = DOMAIN_ACTIONS[domain];
    if (!items || !items.length) return;

    var pageGroup = {
      label: "Page actions · " + domain.toUpperCase(),
      "data-rmc-cmdk-group": "page",
      items: items.map(function (it) {
        return {
          label: it.label,
          url: it.url || null,
          action: it.action || null,
          icon: it.icon || "bi-arrow-right-circle",
          keywords: (it.keywords || "") + " " + domain
        };
      })
    };

    // Avoid double-inject when this script runs twice (e.g. HTMX swap).
    var alreadyHasPageGroup = data.groups.some(function (g) {
      return g && g["data-rmc-cmdk-group"] === "page";
    });
    if (alreadyHasPageGroup) return;

    data.groups.unshift(pageGroup);
    try { node.textContent = JSON.stringify(data); } catch (e) {}
  }

  /* v4.00.29 — Slash-command mode + always-visible Ask-AI line.

     SLASH MODE
       When the user types "/" as the first character in the cmdk input,
       the existing palette filters down to items whose label starts with
       a verb. We seed a "Slash" group with deterministic verb commands so
       slashing always finds something:

         /new student          /go fees           /density
         /new invoice          /go gradebook      /theme
         /new broadcast        /go inbox          /explain  (AI)
         /new event            /go security       /help
         /new staff            /go reports

     ASK-AI LINE
       A pinned "Ask AI" item ALWAYS appears in the data (kept first in
       the Actions group). The existing rmc-command-palette.js also
       synthesises an askAiItem() when no other match exists. The pinned
       version means the user always has a "talk to AI" affordance at
       glance distance.
  */
  function injectSlashAndAi() {
    var node = document.getElementById(DATA_ID);
    if (!node || !node.textContent) return;
    var data;
    try { data = JSON.parse(node.textContent); } catch (e) { return; }
    if (!data || !Array.isArray(data.groups)) return;

    var slashItems = [
      { label: "/new student",      url: "/people/students/new/",         icon: "bi-person-plus",     keywords: "slash new student add enroll" },
      { label: "/new invoice",      url: "/finance/invoices/new/",        icon: "bi-receipt",         keywords: "slash new invoice fee bill" },
      { label: "/new broadcast",    url: "/communication/broadcast/new/", icon: "bi-megaphone",       keywords: "slash new broadcast message announce" },
      { label: "/new event",        url: "/calendar/new/",                icon: "bi-calendar-plus",   keywords: "slash new event calendar" },
      { label: "/new staff",        url: "/people/staff/new/",            icon: "bi-person-badge",    keywords: "slash new staff teacher hire" },
      { label: "/new assessment",   url: "/evals/assessments/new/",       icon: "bi-clipboard-check", keywords: "slash new assessment quiz test" },
      { label: "/go fees",          url: "/finance/",                     icon: "bi-cash-coin",       keywords: "slash go navigate fees finance" },
      { label: "/go gradebook",     url: "/evals/teacher/dashboard/",     icon: "bi-table",           keywords: "slash go navigate gradebook" },
      { label: "/go inbox",         url: "/accounts/notifications/",      icon: "bi-bell",            keywords: "slash go navigate inbox notifications" },
      { label: "/go security",      url: "/accounts/security/",           icon: "bi-shield-check",    keywords: "slash go navigate security posture" },
      { label: "/go reports",       url: "/reports/",                     icon: "bi-bar-chart",       keywords: "slash go navigate reports analytics" },
      { label: "/go attendance",    url: "/attendance/",                  icon: "bi-check2-square",   keywords: "slash go navigate attendance" },
      { label: "/density",          action: "rmc:cmdk:toggle-density",    icon: "bi-arrows-collapse", keywords: "slash density toggle compact comfortable" },
      { label: "/theme",            action: "rmc:cmdk:toggle-theme",      icon: "bi-circle-half",     keywords: "slash theme toggle dark light" },
      { label: "/explain",          action: "rmc:cmdk:ask-ai",            icon: "bi-stars",           keywords: "slash explain ai ask question" },
      { label: "/help",             url: "/help/",                        icon: "bi-life-preserver",  keywords: "slash help support docs" }
    ];

    var alreadyHasSlash = data.groups.some(function (g) {
      return g && g["data-rmc-cmdk-group"] === "slash";
    });
    if (!alreadyHasSlash) {
      data.groups.push({
        label: "Slash · type / to filter verbs",
        "data-rmc-cmdk-group": "slash",
        items: slashItems
      });
    }

    // Pin "Ask AI" to the first Actions group so it stays glance-distance.
    var actionsGroup = null;
    for (var i = 0; i < data.groups.length; i++) {
      if (data.groups[i] && /actions/i.test(data.groups[i].label || "")) {
        actionsGroup = data.groups[i];
        break;
      }
    }
    if (actionsGroup) {
      var hasAskAi = (actionsGroup.items || []).some(function (it) {
        return it && (it.action === "rmc:cmdk:ask-ai" || (it.label || "").toLowerCase().indexOf("ask ai") === 0);
      });
      if (!hasAskAi) {
        actionsGroup.items.unshift({
          label: "Ask AI — describe what you need",
          action: "rmc:cmdk:ask-ai",
          icon: "bi-stars",
          keywords: "ai ask natural language question chat assistant",
          "data-rmc-pinned": "1"
        });
      }
    }

    try { node.textContent = JSON.stringify(data); } catch (e) {}
  }

  // Wire the "rmc:cmdk:toggle-density" action by listening for the custom
  // event the palette dispatches. The palette already fires events for
  // standard action verbs; we add ours alongside.
  function wireCustomActions() {
    document.addEventListener("rmc:cmdk:toggle-density", function () {
      if (window.rmcAdminDensity && typeof window.rmcAdminDensity.toggle === "function") {
        window.rmcAdminDensity.toggle();
      }
    });
    document.addEventListener("rmc:cmdk:toggle-osgrade", function () {
      if (window.rmcOsGrade && typeof window.rmcOsGrade.toggle === "function") {
        window.rmcOsGrade.toggle();
      }
    });
  }

  // v4.00.30/31 — Reads the cmdk data block once for shared config (locale,
  // ai_line_url, etc.). Falls back to safe defaults so we keep running on
  // older shells that haven't picked up the new fields yet.
  function readPlatformCmdkUrl() {
    if (window.RMCPlatformSurface && window.RMCPlatformSurface.url) {
      return (
        window.RMCPlatformSurface.url("ai_line_interpret") ||
        (window.RMCPlatformSurface.read().cmdk || {}).ai_line_url ||
        ""
      ).trim();
    }
    return "";
  }

  function readCmdkConfig() {
    var node = document.getElementById(DATA_ID);
    var fallbackLine = readPlatformCmdkUrl();
    if (!node) {
      return { locale: "", ai_line_url: fallbackLine };
    }
    try {
      var data = JSON.parse(node.textContent || "{}");
      return {
        locale: (data.locale || "").toString(),
        ai_line_url: (data.ai_line_url || fallbackLine || "").trim()
      };
    } catch (e) {
      return { locale: "", ai_line_url: fallbackLine };
    }
  }

  // Map Django LANGUAGE_CODE → BCP-47 tag the Web Speech API expects.
  function resolveSpeechLang(localeFromCmdk) {
    var map = {
      "en": "en-US", "fr": "fr-FR", "es": "es-ES", "pt": "pt-PT", "ar": "ar-EG",
      "sw": "sw-KE", "ha": "ha-NG", "yo": "yo-NG", "ig": "ig-NG",
      "am": "am-ET", "rw": "rw-RW", "zh": "zh-CN", "de": "de-DE", "it": "it-IT",
      "ru": "ru-RU", "ja": "ja-JP"
    };
    var raw = (localeFromCmdk || "").toLowerCase();
    if (!raw) return navigator.language || "en-US";
    if (raw.indexOf("-") > 0) return raw;
    return map[raw] || navigator.language || "en-US";
  }

  // v4.00.30 — Web Speech API voice input. Adds a mic button to the cmdk
  // input bar; clicking starts a one-shot dictation that fills the input
  // and immediately re-fires its `input` event so results update live.
  function wireVoiceInput() {
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return; // Browser lacks support — graceful no-op.
    var input = document.getElementById("rmc-cmdk-input");
    var bar = input && input.closest(".rmc-cmdk__inputbar");
    if (!input || !bar || bar.querySelector(".rmc-cmdk__mic")) return;

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "rmc-cmdk__mic";
    btn.setAttribute("aria-label", "Dictate query");
    btn.title = "Voice search";
    btn.innerHTML = '<i class="bi bi-mic" aria-hidden="true"></i>';

    // Place before the Esc hint so the close affordance stays rightmost.
    var esc = bar.querySelector(".rmc-cmdk__kbd-hint");
    if (esc) {
      bar.insertBefore(btn, esc);
    } else {
      bar.appendChild(btn);
    }

    var rec = null;
    var elapsedTimer = null;
    var startedAt = 0;

    function clearElapsed() {
      if (elapsedTimer) {
        clearInterval(elapsedTimer);
        elapsedTimer = null;
      }
      var existing = btn.querySelector(".rmc-cmdk__mic-elapsed");
      if (existing) existing.remove();
    }

    function startElapsed() {
      clearElapsed();
      startedAt = performance.now ? performance.now() : Date.now();
      var badge = document.createElement("span");
      badge.className = "rmc-cmdk__mic-elapsed";
      badge.textContent = "0.0s";
      btn.appendChild(badge);
      elapsedTimer = setInterval(function () {
        var now = performance.now ? performance.now() : Date.now();
        var s = ((now - startedAt) / 1000).toFixed(1);
        badge.textContent = s + "s";
      }, 100);
    }

    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      try {
        if (rec) {
          rec.stop();
          rec = null;
          btn.classList.remove("is-listening");
          clearElapsed();
          return;
        }
        rec = new SR();
        var cfg = readCmdkConfig();
        rec.lang = resolveSpeechLang(cfg.locale);
        rec.interimResults = true;  // v4.00.35 — live-stream partials so user sees the recognizer "thinking"
        rec.continuous = false;
        rec.maxAlternatives = 1;
        rec.onresult = function (e) {
          // v4.00.35 — assemble final + interim spans. Show interim in
          // real time, lock in finals when the recognizer commits.
          var finalText = "";
          var interimText = "";
          for (var i = 0; i < e.results.length; i++) {
            var r = e.results[i];
            var seg = (r && r[0] && r[0].transcript) || "";
            if (r.isFinal) finalText += seg;
            else interimText += seg;
          }
          var combined = (finalText + interimText).trim();
          if (combined) {
            input.value = combined;
            input.dispatchEvent(new Event("input", { bubbles: true }));
            // Don't .focus() on every interim tick — it can move the caret
            // around mid-typing. Focus once at start instead.
          }
        };
        rec.onend = function () {
          btn.classList.remove("is-listening");
          rec = null;
          clearElapsed();
        };
        rec.onerror = function () {
          btn.classList.remove("is-listening");
          rec = null;
          clearElapsed();
        };
        rec.start();
        btn.classList.add("is-listening");
        startElapsed();
        input.focus();
      } catch (_) {
        btn.classList.remove("is-listening");
        rec = null;
        clearElapsed();
      }
    });
  }

  // v4.00.30 — AI-line interpreter wiring. Listens on the cmdk input and
  // debounces a POST to /api/v1/ai/line-interpret/. When the backend matches
  // a deterministic intent, prepends a single AI suggestion to the results
  // list (or replaces the prior AI row if one exists). Falls back silently
  // on any error — generic cmdk results keep working.
  function wireAiLineInterpreter() {
    var input = document.getElementById("rmc-cmdk-input");
    var list = document.getElementById("rmc-cmdk-list");
    if (!input || !list) return;
    var cfg = readCmdkConfig();
    var endpoint = cfg.ai_line_url || readPlatformCmdkUrl();
    if (!endpoint) return;
    var lastSuggestion = null;
    var t = null;

    function csrfToken() {
      var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
      return m ? decodeURIComponent(m[1]) : "";
    }

    function clearSuggestion() {
      var prior = list.querySelector('[data-rmc-ai-line="1"]');
      if (prior) prior.remove();
      lastSuggestion = null;
    }

    function renderSuggestion(label, url, intent) {
      clearSuggestion();
      var li = document.createElement("li");
      li.setAttribute("role", "option");
      li.setAttribute("data-rmc-ai-line", "1");
      li.className = "rmc-cmdk__item rmc-cmdk__item--ai-line";
      li.innerHTML =
        '<i class="bi bi-magic rmc-cmdk__item-icon" aria-hidden="true"></i>' +
        '<span class="rmc-cmdk__item-label">' + label + '</span>' +
        '<span class="rmc-cmdk__item-hint">AI · ' + (intent || "match") + '</span>';
      li.addEventListener("click", function () { window.location.href = url; });
      li.addEventListener("keydown", function (e) {
        if (e.key === "Enter") window.location.href = url;
      });
      // Prepend so it lands at the top.
      if (list.firstChild) list.insertBefore(li, list.firstChild);
      else list.appendChild(li);
      lastSuggestion = { label: label, url: url, intent: intent };
    }

    function postOnce(q, withAi) {
      return fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify(withAi ? { q: q, ai: "1" } : { q: q })
      }).then(function (r) { return r.ok ? r.json() : null; });
    }

    function fetchInterpretation(q) {
      if (!q || q.length < 4) { clearSuggestion(); return; }
      // Opt into the LLM fallback when the operator double-asks ("?? ") OR
      // the query is long enough to read like a sentence. Cheap heuristic
      // that keeps short navigations latency-tight.
      var explicitAsk = /\?\?\s*$/.test(q);
      var sentenceish = q.length >= 22 && q.split(/\s+/).length >= 4;
      var wantsAi = explicitAsk || sentenceish;
      try {
        postOnce(q, false).then(function (j) {
          if (j && j.matched && j.url) {
            renderSuggestion(j.label || "Open", j.url, j.intent || "");
            return;
          }
          if (wantsAi) {
            return postOnce(q, true).then(function (k) {
              if (k && k.matched && k.url) {
                renderSuggestion(k.label || "Open", k.url, k.intent || "ai");
              } else {
                clearSuggestion();
              }
            });
          }
          clearSuggestion();
        }).catch(function () { /* silent */ });
      } catch (_) { /* silent */ }
    }

    input.addEventListener("input", function () {
      clearTimeout(t);
      var q = input.value;
      t = setTimeout(function () { fetchInterpretation(q); }, 280);
    });
  }

  function bootAugmenter() {
    injectPageActions();
    injectSlashAndAi();
    wireCustomActions();
    // Voice + AI-line wire after the palette has had a tick to mount its DOM.
    setTimeout(function () {
      wireVoiceInput();
      wireAiLineInterpreter();
    }, 0);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootAugmenter);
  } else {
    bootAugmenter();
  }
})();
