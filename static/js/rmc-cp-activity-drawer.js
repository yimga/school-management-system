/**
 * Tier 1 inline badge + Tier 3 incident banner — drawer open, dismiss, 1h snooze.
 */
(function () {
  "use strict";

  var SNOOZE_MS = 60 * 60 * 1000;

  function bannerFingerprint(banner) {
    var severity =
      (banner && banner.getAttribute("data-rmc-cp-incident-severity")) || "warn";
    var textEl = banner && banner.querySelector(".rmc-cp-incident-banner__text");
    var snippet = textEl ? textEl.textContent.trim().slice(0, 80) : "";
    return severity + ":" + snippet;
  }

  function dismissKey(banner) {
    return "rmc-cp-incident-dismiss:" + bannerFingerprint(banner);
  }

  function snoozeKey(banner) {
    return "rmc-cp-incident-snooze-until:" + bannerFingerprint(banner);
  }

  function storageGet(key) {
    try {
      return window.sessionStorage.getItem(key) || window.localStorage.getItem(key);
    } catch (_e) {
      return null;
    }
  }

  function storageSet(key, value, persistent) {
    try {
      if (persistent) {
        window.localStorage.setItem(key, value);
      } else {
        window.sessionStorage.setItem(key, value);
      }
    } catch (_e2) {
      /* ignore */
    }
  }

  function hideBanner(banner) {
    banner.setAttribute("data-rmc-cp-incident-dismissed", "1");
  }

  function isSnoozed(banner) {
    var raw = storageGet(snoozeKey(banner));
    if (!raw) return false;
    var until = parseInt(raw, 10);
    if (!until || Number.isNaN(until)) return false;
    if (Date.now() < until) return true;
    try {
      window.localStorage.removeItem(snoozeKey(banner));
    } catch (_e3) {
      /* ignore */
    }
    return false;
  }

  function initIncidentDismiss() {
    var banner = document.querySelector("[data-rmc-cp-incident-banner='1']");
    if (!banner) return;

    if (storageGet(dismissKey(banner)) === "1" || isSnoozed(banner)) {
      hideBanner(banner);
    }

    var dismissBtn = banner.querySelector("[data-rmc-cp-incident-dismiss='1']");
    if (dismissBtn) {
      dismissBtn.addEventListener("click", function () {
        hideBanner(banner);
        storageSet(dismissKey(banner), "1", false);
      });
    }

    var snoozeBtn = banner.querySelector("[data-rmc-cp-incident-snooze='1']");
    if (snoozeBtn) {
      snoozeBtn.addEventListener("click", function () {
        hideBanner(banner);
        storageSet(snoozeKey(banner), String(Date.now() + SNOOZE_MS), true);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initIncidentDismiss);
  } else {
    initIncidentDismiss();
  }
})();
