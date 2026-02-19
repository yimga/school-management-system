(function () {
  "use strict";

  var weatherIcons = {
    0: "sunny",
    1: "partly_cloudy_day",
    2: "partly_cloudy_day",
    3: "cloud",
    45: "foggy",
    48: "foggy",
    51: "rainy",
    53: "rainy",
    55: "rainy_heavy",
    61: "rainy",
    63: "rainy",
    65: "rainy_heavy",
    71: "ac_unit",
    73: "ac_unit",
    75: "ac_unit",
    80: "rainy",
    81: "rainy_heavy",
    82: "rainy_heavy",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm",
  };

  var weatherDescriptions = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Foggy",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Light showers",
    81: "Showers",
    82: "Heavy showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Heavy thunderstorm",
  };

  var dailyMessages = [
    '"Education is the most powerful weapon which you can use to change the world." - Nelson Mandela',
    '"The beautiful thing about learning is that no one can take it away from you." - B.B. King',
    '"Great things are done by a series of small things brought together." - Vincent Van Gogh',
    '"Success is not final, failure is not fatal: it is the courage to continue that counts." - Winston Churchill',
    '"The only way to do great work is to love what you do." - Steve Jobs',
    '"Believe you can and you are halfway there." - Theodore Roosevelt',
    '"In the middle of difficulty lies opportunity." - Albert Einstein',
    '"Quality is not an act, it is a habit." - Aristotle',
    '"Excellence is not a skill, it is an attitude." - Ralph Marston',
    '"The expert in anything was once a beginner." - Helen Hayes',
  ];

  var monthNames = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
  ];

  var weekdayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var currentDate = new Date();

  function getRoot() {
    return document.querySelector(".admin-dash[data-health-endpoint][data-weather-endpoint]");
  }

  function readJsonScript(id) {
    var raw = document.getElementById(id);
    if (!raw) return null;
    try {
      return JSON.parse(raw.textContent);
    } catch (_error) {
      return null;
    }
  }

  function setSystemStatus(ok, data) {
    var apiEl = document.getElementById("apiHealthStatus");
    var sysEl = document.getElementById("systemStatus");
    var dbConn = document.getElementById("dbConnectionStatus");
    var dbHealth = document.getElementById("dbHealthStatus");

    if (apiEl) {
      apiEl.textContent = ok ? "Operational" : "Degraded";
      apiEl.className = "admin-stat " + (ok ? "admin-stat--success" : "admin-stat--danger");
    }
    if (sysEl) {
      sysEl.textContent = ok ? "Online" : "Attention";
      sysEl.className = "admin-stat " + (ok ? "admin-stat--success" : "admin-stat--danger");
    }
    if (dbConn) {
      var dbOk = Boolean(data && (data.database === "connected" || data.status === "healthy"));
      dbConn.textContent = dbOk ? "Ready" : "Issue";
      dbConn.className = "admin-stat " + (dbOk ? "admin-stat--success" : "admin-stat--danger");
    }
    if (dbHealth) {
      dbHealth.textContent = ok ? "Optimal" : "Check";
      dbHealth.className = "admin-stat " + (ok ? "admin-stat--success" : "admin-stat--danger");
    }
  }

  async function loadSystemHealth(root) {
    var endpoint = root.getAttribute("data-health-endpoint");
    if (!endpoint) return;
    try {
      var response = await fetch(endpoint, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      var data = await response.json();
      var ok = response.ok && data && data.status === "healthy";
      setSystemStatus(ok, data);
    } catch (_error) {
      setSystemStatus(false, null);
    }
  }

  function getWeatherConfig() {
    var defaults = {
      enabled: true,
      label: "Buea, Cameroon",
      latitude: 4.1527,
      longitude: 9.241,
      temperature_unit: "celsius",
      timezone: "Africa/Douala",
    };
    var cfg = readJsonScript("admin-weather-config");
    return Object.assign({}, defaults, cfg || {});
  }

  function setWeatherDisabled(iconEl, tempEl, descEl, unitSymbol) {
    iconEl.textContent = "disabled_by_default";
    tempEl.textContent = "--\u00B0" + unitSymbol;
    descEl.textContent = "Weather disabled";
  }

  function setWeatherFallback(tempEl, descEl, unitSymbol, locationLabel) {
    tempEl.textContent = "--\u00B0" + unitSymbol;
    descEl.textContent = locationLabel;
  }

  async function loadWeather(root) {
    var cfg = getWeatherConfig();
    var endpoint = root.getAttribute("data-weather-endpoint");
    var iconEl = document.getElementById("weatherIcon");
    var tempEl = document.getElementById("weatherTemp");
    var descEl = document.getElementById("weatherDesc");
    if (!endpoint || !iconEl || !tempEl || !descEl) return;

    var tempUnit =
      String(cfg.temperature_unit || "celsius").toLowerCase() === "fahrenheit" ? "fahrenheit" : "celsius";
    var unitSymbol = tempUnit === "fahrenheit" ? "F" : "C";
    var locationLabel = String(cfg.label || "Buea, Cameroon");

    if (!cfg.enabled) {
      setWeatherDisabled(iconEl, tempEl, descEl, unitSymbol);
      return;
    }

    try {
      var response = await fetch(endpoint, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("Weather endpoint unavailable");

      var data = await response.json();
      if (data && data.temperature_unit) {
        tempUnit = String(data.temperature_unit).toLowerCase() === "fahrenheit" ? "fahrenheit" : "celsius";
        unitSymbol = tempUnit === "fahrenheit" ? "F" : "C";
      }
      if (data && data.label) {
        locationLabel = String(data.label);
      }
      if (data && data.enabled === false) {
        setWeatherDisabled(iconEl, tempEl, descEl, unitSymbol);
        return;
      }

      var weather = data && data.weather;
      if (weather && weather.temperature !== undefined && weather.weather_code !== undefined) {
        var temperature = Math.round(Number(weather.temperature));
        var code = Number(weather.weather_code);
        var description = String(weather.description || weatherDescriptions[code] || "Unknown");
        iconEl.textContent = weatherIcons[code] || "partly_cloudy_day";
        tempEl.textContent = temperature + "\u00B0" + unitSymbol;
        descEl.textContent = description + " - " + locationLabel;
      } else {
        setWeatherFallback(tempEl, descEl, unitSymbol, locationLabel);
      }
    } catch (_error) {
      setWeatherFallback(tempEl, descEl, unitSymbol, locationLabel);
    }
  }

  function loadDailyMessage() {
    var now = new Date();
    var start = new Date(now.getFullYear(), 0, 0);
    var dayOfYear = Math.floor((now - start) / 86400000);
    var msg = dailyMessages[dayOfYear % dailyMessages.length];
    var el = document.getElementById("dailyMessage");
    if (el) el.textContent = msg;
  }

  function updateTimestamp() {
    var ts = document.getElementById("timestamp");
    if (ts) ts.textContent = new Date().toLocaleString();
  }

  function updateTodayDate() {
    var todayEl = document.getElementById("todayDate");
    if (!todayEl) return;
    var now = new Date();
    todayEl.textContent = "Today: " + now.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  function generateCalendar() {
    var year = currentDate.getFullYear();
    var month = currentDate.getMonth();
    var monthYear = document.getElementById("monthYear");
    if (monthYear) monthYear.textContent = monthNames[month] + " " + year;

    var firstDay = new Date(year, month, 1).getDay();
    var daysInMonth = new Date(year, month + 1, 0).getDate();
    var today = new Date();
    var grid = document.getElementById("calendarGrid");
    if (!grid) return;

    grid.innerHTML = "";
    weekdayNames.forEach(function (dayName) {
      var header = document.createElement("div");
      header.className = "calendar-grid__header";
      header.textContent = dayName;
      grid.appendChild(header);
    });

    for (var i = 0; i < firstDay; i += 1) {
      var emptyCell = document.createElement("div");
      emptyCell.className = "calendar-day calendar-day--empty";
      grid.appendChild(emptyCell);
    }

    for (var day = 1; day <= daysInMonth; day += 1) {
      var cell = document.createElement("div");
      cell.className = "calendar-day";
      cell.textContent = day;
      if (today.getFullYear() === year && today.getMonth() === month && today.getDate() === day) {
        cell.classList.add("calendar-day--today");
      }
      grid.appendChild(cell);
    }
  }

  function bindCalendarControls() {
    var controls = document.querySelectorAll("[data-calendar-nav]");
    controls.forEach(function (button) {
      button.addEventListener("click", function () {
        var direction = button.getAttribute("data-calendar-nav");
        if (direction === "prev") {
          currentDate.setMonth(currentDate.getMonth() - 1);
        } else if (direction === "next") {
          currentDate.setMonth(currentDate.getMonth() + 1);
        } else {
          return;
        }
        generateCalendar();
      });
    });
  }

  function init() {
    document.body.dataset.dashboardPage = "admin-security";
    var root = getRoot();
    if (!root) return;

    bindCalendarControls();
    generateCalendar();
    updateTimestamp();
    updateTodayDate();
    loadSystemHealth(root);
    loadWeather(root);
    loadDailyMessage();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
