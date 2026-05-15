(function () {
  var script = document.currentScript;
  var host = script ? script.previousElementSibling : null;
  if (!host || !host.classList || !host.classList.contains("ai-draft-inline")) return;

  var btn = host.querySelector('[data-action="generate-draft"]');
  var statusEl = host.querySelector('[data-role="status"]');
  var textarea = document.getElementById(host.dataset.textareaId || "");
  if (!btn || !statusEl || !textarea) return;

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
    btn.disabled = true;
    statusEl.textContent = host.dataset.statusDrafting || "Drafting...";
    fetch(host.dataset.draftEndpoint, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf()
      },
      body: JSON.stringify({
        intent: host.dataset.intent,
        existing: textarea.value
      })
    }).then(function (response) {
      return response.json();
    }).then(function (data) {
      if (data && data.draft) {
        textarea.value = data.draft;
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
        statusEl.textContent = host.dataset.statusInserted || "Draft inserted - please review.";
      } else {
        statusEl.textContent = data && data.error
          ? data.error
          : host.dataset.statusEmpty || "No draft returned.";
      }
    }).catch(function () {
      statusEl.textContent = host.dataset.statusUnavailable || "Draft service unavailable.";
    }).finally(function () {
      btn.disabled = false;
    });
  });
})();
