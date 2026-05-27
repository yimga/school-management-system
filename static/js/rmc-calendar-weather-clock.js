(function () {
  "use strict";

  function readTimezone(root, attr, fallback) {
    var value = String((root && root.getAttribute(attr)) || fallback || "UTC").trim();
    try {
      new Intl.DateTimeFormat("en-US", { timeZone: value });
      return value;
    } catch (e) {
      return "UTC";
    }
  }

  function formatInZone(date, timeZone, options) {
    var locale = document.documentElement.lang || navigator.language || "en-US";
    return new Intl.DateTimeFormat(locale, Object.assign({ timeZone: timeZone }, options)).format(date);
  }

  function updateSection(section) {
    var nowNode = section.querySelector("[data-rmc-cal-weather-now]");
    if (!nowNode) return;
    var localTz = readTimezone(section, "data-local-timezone", "UTC");
    var globalTz = readTimezone(section, "data-global-timezone", "UTC");
    var dateEl = nowNode.querySelector(".tp-cal-weather__now-date");
    var timeEl = nowNode.querySelector(".tp-cal-weather__now-time");
    var globalEl = nowNode.querySelector(".tp-cal-weather__now-global");
    var now = new Date();
    if (dateEl) {
      dateEl.textContent = formatInZone(now, localTz, {
        weekday: "long",
        month: "short",
        day: "numeric"
      });
    }
    if (timeEl) {
      timeEl.textContent = formatInZone(now, localTz, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
      });
    }
    if (globalEl) {
      if (localTz === globalTz) {
        globalEl.textContent = "";
        globalEl.hidden = true;
      } else {
        globalEl.hidden = false;
        globalEl.textContent = "· " + formatInZone(now, globalTz, {
          hour: "2-digit",
          minute: "2-digit",
          timeZoneName: "short"
        });
      }
    }
  }

  var sections = document.querySelectorAll("[data-rmc-tp-cal-weather]");
  if (!sections.length) return;
  sections.forEach(updateSection);
  window.setInterval(function () {
    sections.forEach(updateSection);
  }, 1000);
})();
