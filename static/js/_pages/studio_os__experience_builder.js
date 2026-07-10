/*
 * Studio OS — canvas-first Experience builder (Phase 1 progressive enhancement).
 *
 * The region outline links and the Draft/Live toggle are real ?region=/?view=
 * navigation and work with NO JavaScript (the server re-renders the scoped
 * inspector + canvas strip). This script upgrades them to in-place fragment
 * swaps so selecting a region does not reload the whole shell (keeping the
 * live-preview iframe and scroll position). Any failure falls back to a normal
 * full navigation — never a dead end.
 *
 * No inline script, no eval — CSP-safe.
 */
(function () {
  "use strict";

  var OUTLINE = "[data-rmc-experience-outline]";
  var INSPECTOR = "[data-rmc-experience-inspector]";
  var STRIP = "[data-rmc-experience-canvas-strip]";

  function q(sel) {
    return document.querySelector(sel);
  }

  if (!q(OUTLINE)) {
    return;
  }

  function swap(sel, doc) {
    var cur = q(sel);
    var next = doc.querySelector(sel);
    if (cur && next) {
      cur.replaceWith(next);
    }
  }

  function apply(html) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    if (!doc.querySelector(OUTLINE)) {
      throw new Error("no-fragment");
    }
    // Order: strip + inspector first (they may be absent from the outline node),
    // then the outline itself (which carries the delegated click handler).
    swap(STRIP, doc);
    swap(INSPECTOR, doc);
    swap(OUTLINE, doc);
    bind();
  }

  function go(url, push) {
    fetch(url, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "fetch" }
    })
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("http-" + resp.status);
        }
        return resp.text();
      })
      .then(function (html) {
        apply(html);
        if (push !== false) {
          try {
            history.pushState({ rmcExperienceUrl: url }, "", url);
          } catch (err) {
            /* history unavailable — the swap already happened */
          }
        }
      })
      .catch(function () {
        window.location.href = url;
      });
  }

  function onClick(evt) {
    var link = evt.target.closest(
      "[data-rmc-experience-region],[data-rmc-experience-view]"
    );
    if (!link) {
      return;
    }
    var href = link.getAttribute("href");
    if (!href) {
      return;
    }
    // Let modified clicks (new tab, etc.) behave normally.
    if (evt.metaKey || evt.ctrlKey || evt.shiftKey || evt.altKey) {
      return;
    }
    evt.preventDefault();
    go(link.href, true);
  }

  function bind() {
    var outline = q(OUTLINE);
    if (outline && outline.dataset.rmcExperienceBound !== "1") {
      outline.addEventListener("click", onClick);
      outline.dataset.rmcExperienceBound = "1";
    }
  }

  bind();

  window.addEventListener("popstate", function () {
    go(window.location.href, false);
  });
})();
