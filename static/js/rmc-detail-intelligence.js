/*
 * rmc-detail-intelligence.js — Surface 8: detail / profile field intelligence.
 *
 * Detail pages (student / teacher / invoice / profile / record drawers) already
 * have a key-value grammar (.rmc-kv => <dl><dt><dd>) and a sticky section-nav
 * observer (rmc-section-nav.js). What's missing is the field-level polish that
 * completes the nav -> list -> DETAIL journey:
 *
 *   1. copy-to-clipboard is wired for the MFA secret ONLY ([data-rmc-copy-mfa-
 *      secret]); you can't copy a student's admission number, email, or phone
 *      from a detail page without selecting the text by hand.
 *   2. emails / phones render as inert plain text — not mailto: / tel: links.
 *   3. empty field values render as a blank gap that reads as "broken".
 *   4. the section-nav observer exists, but every link has to be hand-authored.
 *
 * This engine enhances field values IN PLACE (composing the existing grammar)
 * and auto-fills an author-placed section nav from the page's existing section
 * anchors. It attaches to .rmc-kv <dd> values and [data-rmc-field] / explicit
 * [data-rmc-copy] elements; it never touches a cell that already holds child
 * elements (so curated markup is preserved). CSP-safe (createElement +
 * textContent), self-guarded, no-op when its hooks are absent.
 */
(function () {
  "use strict";

  if (window.__rmcDetailIntelligenceInit) {
    return;
  }
  window.__rmcDetailIntelligenceInit = true;

  function readConfig() {
    var el = document.getElementById("rmc-detail-config");
    if (!el) {
      return { intelligence: true, copy: true, actionable: true, emptyFields: true, sectionNav: true };
    }
    try {
      return JSON.parse(el.textContent || "{}");
    } catch (e) {
      return { intelligence: true, copy: true, actionable: true, emptyFields: true, sectionNav: true };
    }
  }

  var cfg = readConfig();
  if (cfg.intelligence === false) {
    return;
  }

  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  var PHONE_RE = /^[+(]?[\d][\d\s().-]{6,}$/;
  // ID / code: starts alnum, >=6 chars, allows / _ - and MUST contain a digit
  // (so plain words like "Active" or "Leadership" don't sprout a copy button).
  var CODE_RE = /^(?=.*\d)[A-Za-z0-9][A-Za-z0-9/_-]{5,}$/;

  function cellText(el) {
    return (el.textContent || "").trim();
  }

  function hasElementChild(el) {
    return !!(el.children && el.children.length > 0);
  }

  // ---- Copy-to-clipboard (generalises the MFA-only copy) -------------------
  function makeCopyButton(value) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "rmc-detail-copy";
    btn.setAttribute("aria-label", "Copy to clipboard");
    btn.title = "Copy";
    var i = document.createElement("i");
    i.className = "bi bi-clipboard";
    i.setAttribute("aria-hidden", "true");
    btn.appendChild(i);
    btn.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      function done() {
        i.className = "bi bi-check2";
        btn.classList.add("is-copied");
        window.setTimeout(function () {
          i.className = "bi bi-clipboard";
          btn.classList.remove("is-copied");
        }, 1400);
      }
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(value).then(done, function () {});
        }
      } catch (e) {
        /* copy is best-effort */
      }
    });
    return btn;
  }

  function isCopyable(text) {
    return EMAIL_RE.test(text) || PHONE_RE.test(text) || CODE_RE.test(text);
  }

  // ---- Actionable: wrap an email/phone value in a mailto:/tel: link --------
  function actionLink(text) {
    if (EMAIL_RE.test(text)) {
      var a = document.createElement("a");
      a.className = "rmc-detail-action";
      a.setAttribute("href", "mailto:" + text);
      a.textContent = text;
      return a;
    }
    if (PHONE_RE.test(text)) {
      var tel = text.replace(/[\s().-]/g, "");
      var link = document.createElement("a");
      link.className = "rmc-detail-action";
      link.setAttribute("href", "tel:" + tel);
      link.textContent = text;
      return link;
    }
    return null;
  }

  function enhanceValueCell(cell, explicitCopy) {
    if (cell.getAttribute("data-rmc-detail-done")) {
      return;
    }
    var text = cellText(cell);

    // Empty-field treatment first (nothing else applies to an empty cell).
    if (!text && !hasElementChild(cell)) {
      if (cfg.emptyFields !== false) {
        cell.setAttribute("data-rmc-detail-done", "1");
        var dash = document.createElement("span");
        dash.className = "rmc-detail-empty";
        dash.textContent = "—";
        dash.setAttribute("aria-label", "Not set");
        cell.appendChild(dash);
      }
      return;
    }

    // Only enhance plain-text cells — never clobber curated markup.
    if (hasElementChild(cell)) {
      return;
    }

    var wantCopy = explicitCopy || (cfg.copy !== false && isCopyable(text));
    var link = cfg.actionable !== false ? actionLink(text) : null;
    if (!wantCopy && !link) {
      return;
    }

    cell.setAttribute("data-rmc-detail-done", "1");
    cell.textContent = "";
    if (link) {
      cell.appendChild(link);
    } else {
      cell.appendChild(document.createTextNode(text));
    }
    if (wantCopy) {
      cell.appendChild(document.createTextNode(" "));
      cell.appendChild(makeCopyButton(text));
      cell.classList.add("rmc-detail-has-copy");
    }
  }

  function enhanceFields() {
    var seen = [];
    function collect(sel) {
      var nodes = document.querySelectorAll(sel);
      for (var i = 0; i < nodes.length; i++) {
        if (seen.indexOf(nodes[i]) === -1) {
          seen.push(nodes[i]);
        }
      }
    }
    // Canonical detail value cells only: the .rmc-kv definition-list <dd>. We do
    // NOT key off [data-rmc-field] — that attribute marks a FORM-field wrapper
    // (a <div> holding a label + input), a different domain entirely.
    collect(".rmc-kv > dd");
    for (var i = 0; i < seen.length; i++) {
      try {
        enhanceValueCell(seen[i], false);
      } catch (e) {
        /* one bad cell must not break the rest */
      }
    }
    // Explicit opt-in copy targets (any element, any value).
    if (cfg.copy !== false) {
      var explicit = document.querySelectorAll("[data-rmc-copy]");
      for (var j = 0; j < explicit.length; j++) {
        try {
          enhanceValueCell(explicit[j], true);
        } catch (e) {
          /* skip */
        }
      }
    }
  }

  // ---- Section-nav auto-fill (composes rmc-section-nav.js) ------------------
  // Author places ONE empty <aside class="rmc-section-nav" data-rmc-section-nav-
  // auto> (or any [data-rmc-section-nav-auto]); the engine builds the link list
  // from the page's existing [data-rmc-section-anchor] sections. The existing
  // observer then drives active-state — no layout guessing, no hand-authored
  // <li> per section.
  function sectionLabel(section, idx) {
    var explicit = section.getAttribute("data-rmc-section-nav-label");
    if (explicit) {
      return explicit;
    }
    var heading = section.querySelector("h1, h2, h3, h4, [data-rmc-section-title]");
    if (heading && cellText(heading)) {
      return cellText(heading);
    }
    var aria = section.getAttribute("aria-label");
    return aria || "Section " + (idx + 1);
  }

  function ensureId(section, idx) {
    if (section.id) {
      return section.id;
    }
    var id = "rmc-section-" + (idx + 1);
    section.id = id;
    return id;
  }

  // The existing rmc-section-nav.js init() has already run by the time this
  // engine mounts (it loads earlier), so it can't observe a nav we build now.
  // The engine therefore owns active-state + smooth-scroll for ITS OWN nav.
  function observeNav(pairs) {
    pairs.forEach(function (p) {
      p.link.addEventListener("click", function (e) {
        var target = document.getElementById(p.id);
        if (!target) {
          return;
        }
        e.preventDefault();
        var offset = 72;
        try {
          var chrome = parseInt(
            getComputedStyle(document.documentElement).getPropertyValue("--rmc-cp-chrome-offset"),
            10
          );
          if (!isNaN(chrome)) {
            offset = chrome + 12;
          }
        } catch (err) {
          /* default offset */
        }
        var top = target.getBoundingClientRect().top + window.pageYOffset - offset;
        window.scrollTo({ top: top, behavior: "smooth" });
      });
    });
    if (typeof IntersectionObserver !== "function") {
      return;
    }
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) {
            return;
          }
          pairs.forEach(function (p) {
            if (p.section === entry.target) {
              p.link.classList.add("is-active");
            } else {
              p.link.classList.remove("is-active");
            }
          });
        });
      },
      { rootMargin: "-30% 0px -60% 0px", threshold: 0 }
    );
    pairs.forEach(function (p) {
      io.observe(p.section);
    });
  }

  function fillSectionNav() {
    if (cfg.sectionNav === false) {
      return;
    }
    var mounts = document.querySelectorAll("[data-rmc-section-nav-auto]");
    if (!mounts.length) {
      return;
    }
    var sections = [];
    var all = document.querySelectorAll("[data-rmc-section-anchor]");
    for (var i = 0; i < all.length; i++) {
      if (!all[i].getAttribute("data-rmc-section-nav-skip")) {
        sections.push(all[i]);
      }
    }
    if (sections.length < 2) {
      return; // not worth a nav
    }
    for (var m = 0; m < mounts.length; m++) {
      var mount = mounts[m];
      if (mount.getAttribute("data-rmc-detail-done") || mount.querySelector(".rmc-section-nav__list")) {
        continue;
      }
      mount.setAttribute("data-rmc-detail-done", "1");
      mount.classList.add("rmc-section-nav");

      var labelText = mount.getAttribute("data-rmc-section-nav-label") || "On this page";
      var label = document.createElement("div");
      label.className = "rmc-section-nav__label";
      label.textContent = labelText;

      var list = document.createElement("ul");
      list.className = "rmc-section-nav__list";
      var pairs = [];
      for (var s = 0; s < sections.length; s++) {
        var id = ensureId(sections[s], s);
        var li = document.createElement("li");
        var a = document.createElement("a");
        a.setAttribute("href", "#" + id);
        a.textContent = sectionLabel(sections[s], s);
        li.appendChild(a);
        list.appendChild(li);
        pairs.push({ id: id, link: a, section: sections[s] });
      }
      mount.appendChild(label);
      mount.appendChild(list);
      observeNav(pairs);
    }
  }

  function init() {
    try {
      enhanceFields();
    } catch (e) {
      /* chrome must survive */
    }
    try {
      fillSectionNav();
    } catch (e) {
      /* chrome must survive */
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
