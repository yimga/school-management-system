(function () {
  "use strict";
  if (window.__runmycampusHeaderContextInit) return;
  window.__runmycampusHeaderContextInit = true;

  var strips = Array.prototype.slice.call(document.querySelectorAll("[data-header-context]"));
  if (!strips.length) return;

  var weatherIconClasses = {
    0: "bi-sun-fill", 1: "bi-brightness-high", 2: "bi-cloud-sun", 3: "bi-cloud",
    45: "bi-cloud-fog2", 48: "bi-cloud-fog2",
    51: "bi-cloud-drizzle", 53: "bi-cloud-drizzle", 55: "bi-cloud-rain",
    61: "bi-cloud-rain", 63: "bi-cloud-rain", 65: "bi-cloud-rain-heavy",
    71: "bi-cloud-snow", 73: "bi-cloud-snow", 75: "bi-cloud-snow",
    80: "bi-cloud-rain", 81: "bi-cloud-rain", 82: "bi-cloud-rain-heavy",
    95: "bi-cloud-lightning", 96: "bi-cloud-lightning", 99: "bi-cloud-lightning"
  };

  var quotes = [
    "Stay consistent and keep building.",
    "Clarity drives better execution.",
    "Small daily gains compound fast.",
    "Discipline protects your momentum.",
    "Finish the important task first.",
    "Systems beat last-minute effort.",
    "Progress is built one step at a time."
  ];

  function readTimezone(strip, attr) {
    var value = (strip && strip.getAttribute(attr)) || "";
    value = String(value).trim();
    if (!value) return "UTC";
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

  function isCompact(strip) {
    return strip.getAttribute("data-rmc-header-context-compact") === "1"
      || Boolean(strip.closest("[data-rmc-header-context-compact='1']"));
  }

  function updateDateTime() {
    var now = new Date();
    strips.forEach(function (strip) {
      var localTz = readTimezone(strip, "data-local-timezone");
      var globalTz = readTimezone(strip, "data-global-timezone");
      var localTarget = strip.querySelector("[data-header-datetime]");
      var compactTarget = strip.querySelector("[data-header-datetime-compact]");
      var globalTarget = strip.querySelector("[data-header-datetime-global]");
      var compact = isCompact(strip);
      var localDate = formatInZone(now, localTz, {
        weekday: "short",
        month: "short",
        day: "numeric"
      });
      var timeOptions = compact
        ? { hour: "2-digit", minute: "2-digit" }
        : { hour: "2-digit", minute: "2-digit", second: "2-digit" };
      var localTime = formatInZone(now, localTz, timeOptions);
      if (localTarget) {
        localTarget.textContent = localDate + " | " + localTime;
      }
      if (compactTarget) {
        compactTarget.textContent = localTime;
      }
      if (globalTarget) {
        if (localTz === globalTz) {
          globalTarget.hidden = true;
          globalTarget.textContent = "";
        } else {
          globalTarget.hidden = false;
          globalTarget.textContent = formatInZone(now, globalTz, {
            hour: "2-digit",
            minute: "2-digit",
            timeZoneName: "short"
          });
        }
      }
    });
  }

  function updateQuote() {
    var now = new Date();
    var hourlySlot = Math.floor(now.getTime() / (60 * 60 * 1000));
    var quote = quotes[hourlySlot % quotes.length];
    strips.forEach(function (strip) {
      var target = strip.querySelector("[data-header-quote]");
      if (target) target.textContent = quote;
    });
  }

  function getWeatherConfig() {
    var first = strips[0];
    var endpoint = (first && first.getAttribute("data-weather-endpoint")) || "";
    var lat = parseFloat(first && first.getAttribute("data-weather-lat"));
    var lon = parseFloat(first && first.getAttribute("data-weather-lon"));
    var unit = (first && first.getAttribute("data-weather-unit")) || "celsius";
    if (Number.isNaN(lat)) lat = 4.1527;
    if (Number.isNaN(lon)) lon = 9.2410;
    if (unit !== "fahrenheit") unit = "celsius";
    return { endpoint: endpoint, lat: lat, lon: lon, unit: unit };
  }

  function setWeatherFallback(label) {
    strips.forEach(function (strip) {
      var icon = strip.querySelector("[data-header-weather-icon]");
      var temp = strip.querySelector("[data-header-weather-temp]");
      var desc = strip.querySelector("[data-header-weather-desc]");
      if (icon) icon.className = "header-context-icon bi bi-cloud";
      if (temp) temp.textContent = "--";
      if (desc) desc.textContent = label || "Weather unavailable";
    });
  }

  function updateWeather() {
    var config = getWeatherConfig();
    if (!config.endpoint) {
      setWeatherFallback("Weather unavailable");
      return;
    }

    fetch(config.endpoint, {
      method: "GET",
      credentials: "same-origin",
      headers: { "Accept": "application/json" }
    })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        var weather = data && data.weather;
        if (!data || data.enabled === false || !weather) {
          setWeatherFallback((data && data.label) || "Weather unavailable");
          return;
        }
        var temp = Math.round(Number(weather.temperature));
        var code = Number(weather.weather_code);
        var unit = String(data.temperature_unit || config.unit).toLowerCase() === "fahrenheit" ? "fahrenheit" : "celsius";
        var unitSymbol = unit === "fahrenheit" ? "F" : "C";
        var degreeSymbol = "\u00B0";
        var descText = String(weather.description || "Weather");
        var label = String(data.label || "").trim();
        strips.forEach(function (strip) {
          var icon = strip.querySelector("[data-header-weather-icon]");
          var tempNode = strip.querySelector("[data-header-weather-temp]");
          var desc = strip.querySelector("[data-header-weather-desc]");
          if (icon) {
            var iconClass = weatherIconClasses[code] || "bi-cloud";
            icon.className = "header-context-icon bi " + iconClass;
          }
          if (tempNode) tempNode.textContent = String(temp) + degreeSymbol + unitSymbol;
          if (desc) desc.textContent = label ? label + " · " + descText : descText;
        });
      })
      .catch(function () {
        setWeatherFallback("Weather unavailable");
      });
  }

  updateDateTime();
  updateQuote();
  updateWeather();

  window.setInterval(updateDateTime, 1000);
  window.setInterval(updateQuote, 15 * 60 * 1000);
  window.setInterval(updateWeather, 15 * 60 * 1000);
})();
