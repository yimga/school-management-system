  (function() {
    var root = document.querySelector('.weather-marquee-container[data-weather-endpoint]');
    if (!root) return;

    var weatherIcons = {
      0: 'sunny',
      1: 'partly_cloudy_day',
      2: 'partly_cloudy_day',
      3: 'cloud',
      45: 'foggy',
      48: 'foggy',
      51: 'rainy',
      53: 'rainy',
      55: 'rainy_heavy',
      61: 'rainy',
      63: 'rainy',
      65: 'rainy_heavy',
      71: 'ac_unit',
      73: 'ac_unit',
      75: 'ac_unit',
      80: 'rainy',
      81: 'rainy_heavy',
      82: 'rainy_heavy',
      95: 'thunderstorm',
      96: 'thunderstorm',
      99: 'thunderstorm'
    };

    function setText(id, value) {
      var node = document.getElementById(id);
      if (node) node.textContent = value;
    }

    function applyWeather(payload) {
      var tempUnit = String((payload && payload.temperature_unit) || 'celsius').toLowerCase() === 'fahrenheit' ? 'F' : 'C';
      var label = String((payload && payload.label) || 'Weather');
      var weather = payload && payload.weather;

      if (!payload || payload.enabled === false || !weather) {
        setText('marqueeWeatherIcon', 'disabled_by_default');
        setText('marqueeWeatherIcon2', 'disabled_by_default');
        setText('marqueeWeatherTemp', '--\u00B0' + tempUnit);
        setText('marqueeWeatherTemp2', '--\u00B0' + tempUnit);
        setText('marqueeWeatherDesc', label);
        setText('marqueeWeatherDesc2', label);
        return;
      }

      var code = Number(weather.weather_code);
      var icon = weatherIcons[code] || 'partly_cloudy_day';
      var description = String(weather.description || 'Unknown');
      var temperature = Number(weather.temperature);
      var tempText = Number.isFinite(temperature) ? (Math.round(temperature) + '\u00B0' + tempUnit) : ('--\u00B0' + tempUnit);
      var descriptionText = description + ' - ' + label;

      setText('marqueeWeatherIcon', icon);
      setText('marqueeWeatherIcon2', icon);
      setText('marqueeWeatherTemp', tempText);
      setText('marqueeWeatherTemp2', tempText);
      setText('marqueeWeatherDesc', descriptionText);
      setText('marqueeWeatherDesc2', descriptionText);
    }

    async function loadWeatherForMarquee() {
      var endpoint = root.getAttribute('data-weather-endpoint');
      if (!endpoint) return;
      try {
        var response = await fetch(endpoint, {
          credentials: 'same-origin',
          headers: { 'Accept': 'application/json' }
        });
        if (!response.ok) {
          throw new Error('Weather endpoint request failed');
        }
        var data = await response.json();
        applyWeather(data || {});
      } catch (_error) {
        applyWeather({
          enabled: true,
          label: 'Weather',
          temperature_unit: 'celsius',
          weather: null
        });
      }
    }

    function loadDailyQuoteForMarquee() {
      var messages = [
        '"Great things are done by a series of small things brought together." - Vincent Van Gogh',
        '"Education is the most powerful weapon which you can use to change the world." - Nelson Mandela',
        '"The beautiful thing about learning is that no one can take it away from you." - B.B. King',
        '"Success is not final, failure is not fatal: it is the courage to continue that counts." - Winston Churchill',
        '"The only way to do great work is to love what you do." - Steve Jobs',
        '"Believe you can and you are halfway there." - Theodore Roosevelt',
        '"In the middle of difficulty lies opportunity." - Albert Einstein',
        '"Quality is not an act, it is a habit." - Aristotle',
        '"Excellence is not a skill, it is an attitude." - Ralph Marston',
        '"The expert in anything was once a beginner." - Helen Hayes',
      ];
      var now = new Date();
      var start = new Date(now.getFullYear(), 0, 0);
      var dayOfYear = Math.floor((now - start) / 86400000);
      var quote = messages[dayOfYear % messages.length];
      setText('marqueeQuote', quote);
      setText('marqueeQuote2', quote);
    }

    function initWeatherMarquee() {
      loadWeatherForMarquee();
      loadDailyQuoteForMarquee();
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initWeatherMarquee);
    } else {
      initWeatherMarquee();
    }
  })();
