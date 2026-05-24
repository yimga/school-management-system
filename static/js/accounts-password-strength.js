(function () {
  "use strict";
  var form = document.querySelector('form[action=""][method="post"], form[method="post"]');
  var input = document.getElementById("id_new_password1");
  if (!input || !form) return;

  var hidden = document.createElement("input");
  hidden.type = "hidden";
  hidden.name = "password_strength_score";
  hidden.id = "password_strength_score";
  hidden.value = "0";
  form.appendChild(hidden);

  var meter = document.createElement("div");
  meter.className = "small mt-1";
  meter.setAttribute("aria-live", "polite");
  meter.dataset.rmcPasswordMeter = "1";
  input.parentNode.appendChild(meter);

  function label(score) {
    var labels = ["Very weak", "Weak", "Fair", "Strong", "Very strong"];
    return labels[score] || "";
  }

  function update() {
    var val = input.value || "";
    var score = 0;
    if (window.zxcvbn && val) {
      score = window.zxcvbn(val).score;
    }
    hidden.value = String(score);
    meter.textContent = val ? "Strength: " + label(score) + " (" + score + "/4)" : "";
    input.setAttribute("aria-invalid", score < 3 && val.length > 0 ? "true" : "false");
  }

  input.addEventListener("input", update);
  form.addEventListener("submit", function (e) {
    update();
    if (parseInt(hidden.value, 10) < 3 && input.value) {
      e.preventDefault();
      meter.textContent = "Choose a stronger password before saving.";
    }
  });
})();
