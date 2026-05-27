(function() {
  "use strict";
  var root = document.getElementById("backendDatetimeWeather");
  if (!root) return;

  var monthYearEl = document.getElementById("backendDtwMonthYear");
  var timeEl = document.getElementById("backendDtwTime");
  var iconEl = document.getElementById("backendDtwWeatherIcon");
  var tempEl = document.getElementById("backendDtwTemp");
  var locEl = document.getElementById("backendDtwLocation");

  var weatherIconClasses = {
    0: "bi-sun-fill", 1: "bi-brightness-high", 2: "bi-cloud-sun", 3: "bi-cloud",
    45: "bi-cloud-fog2", 48: "bi-cloud-fog2",
    51: "bi-cloud-drizzle", 53: "bi-cloud-drizzle", 55: "bi-cloud-rain",
    61: "bi-cloud-rain", 63: "bi-cloud-rain", 65: "bi-cloud-rain-heavy",
    71: "bi-cloud-snow", 73: "bi-cloud-snow", 75: "bi-cloud-snow",
    80: "bi-cloud-rain", 81: "bi-cloud-rain", 82: "bi-cloud-rain-heavy",
    95: "bi-cloud-lightning", 96: "bi-cloud-lightning", 99: "bi-cloud-lightning"
  };

  function readTimezone(attr, fallback) {
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

  function updateDateTime() {
    var now = new Date();
    var localTz = readTimezone("data-local-timezone", "UTC");
    var globalTz = readTimezone("data-global-timezone", "UTC");
    if (monthYearEl) {
      monthYearEl.textContent = formatInZone(now, localTz, { month: "long", year: "numeric" });
    }
    if (timeEl) {
      timeEl.textContent = formatInZone(now, localTz, {
        hour: "numeric",
        minute: "2-digit",
        second: "2-digit",
        hour12: true
      });
    }
    var globalLine = document.getElementById("backendDtwGlobalTime");
    if (globalLine) {
      if (localTz === globalTz) {
        globalLine.textContent = "";
        globalLine.hidden = true;
      } else {
        globalLine.hidden = false;
        globalLine.textContent = formatInZone(now, globalTz, {
          hour: "2-digit",
          minute: "2-digit",
          timeZoneName: "short"
        });
      }
    }
  }

  function getWeatherConfig() {
    var endpoint = root.getAttribute("data-weather-endpoint") || "";
    var lat = parseFloat(root.getAttribute("data-weather-lat"));
    var lon = parseFloat(root.getAttribute("data-weather-lon"));
    var unit = (root.getAttribute("data-weather-unit") || "celsius").toLowerCase();
    if (Number.isNaN(lat)) lat = 4.1527;
    if (Number.isNaN(lon)) lon = 9.2410;
    if (unit !== "fahrenheit") unit = "celsius";
    return { endpoint: endpoint, lat: lat, lon: lon, unit: unit };
  }

  function updateWeather() {
    var config = getWeatherConfig();
    if (!config.endpoint) {
      if (tempEl) tempEl.textContent = "--\u00B0";
      return;
    }

    fetch(config.endpoint, {
      method: "GET",
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    })
      .then(function(r) { return r.ok ? r.json() : null; })
      .then(function(data) {
        var weather = data && data.weather;
        if (!data || data.enabled === false || !weather || !tempEl) {
          if (tempEl) tempEl.textContent = "--\u00B0";
          return;
        }
        var temp = Math.round(Number(weather.temperature));
        var code = Number(weather.weather_code);
        var unit = String(data.temperature_unit || config.unit).toLowerCase() === "fahrenheit" ? "fahrenheit" : "celsius";
        var sym = unit === "fahrenheit" ? "\u00B0F" : "\u00B0";
        tempEl.textContent = temp + sym;
        if (iconEl) {
          var cls = weatherIconClasses[code] || "bi-cloud-sun";
          iconEl.className = "bi " + cls + " backend-dtw__weather-icon";
        }
      })
      .catch(function() {
        if (tempEl) tempEl.textContent = "--\u00B0";
      });
  }

  if (locEl && root.getAttribute("data-weather-label")) {
    locEl.textContent = root.getAttribute("data-weather-label");
  }

  updateDateTime();
  updateWeather();
  setInterval(updateDateTime, 1000);
  setInterval(updateWeather, 15 * 60 * 1000);
})();
