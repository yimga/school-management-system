(function () {
  var btn = document.getElementById("lesson-outline-generate");
  if (!btn) return;
  var endpoint = btn.getAttribute("data-endpoint");
  var statusEl = document.getElementById("lesson-outline-status");
  var intentEl = document.getElementById("lesson-outline-intent");
  var subjectEl = document.getElementById("lesson-outline-subject");
  var gradeEl = document.getElementById("lesson-outline-grade");
  var resultEl = document.getElementById("lesson-outline-result");
  if (!endpoint || !intentEl || !resultEl) return;

  function csrf() {
    var name = "csrftoken=";
    var parts = (document.cookie || "").split(";");
    for (var i = 0; i < parts.length; i += 1) {
      var cookie = parts[i].trim();
      if (cookie.indexOf(name) === 0) return cookie.substring(name.length);
    }
    return "";
  }

  btn.addEventListener("click", function () {
    var intent = (intentEl.value || "").trim();
    if (!intent) {
      if (statusEl) statusEl.textContent = "Describe the lesson focus first.";
      return;
    }
    btn.disabled = true;
    if (statusEl) statusEl.textContent = "Drafting...";
    fetch(endpoint, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf()
      },
      body: JSON.stringify({
        intent: intent,
        subject: subjectEl ? subjectEl.value : "",
        grade_level: gradeEl ? gradeEl.value : ""
      })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.draft) {
          resultEl.value = data.draft;
          if (statusEl) statusEl.textContent = "Outline ready — review before use.";
        } else if (statusEl) {
          statusEl.textContent = (data && data.error) || "No draft returned.";
        }
      })
      .catch(function () {
        if (statusEl) statusEl.textContent = "Draft service unavailable.";
      })
      .finally(function () {
        btn.disabled = false;
      });
  });
})();
