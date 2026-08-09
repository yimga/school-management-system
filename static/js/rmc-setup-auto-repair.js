(function () {
  "use strict";
  function escapeHtml(value) { var node = document.createElement("span"); node.textContent = String(value || ""); return node.innerHTML; }
  document.addEventListener("submit", async function (event) {
    var form = event.target.closest("[data-rmc-auto-repair-form]");
    if (!form) return;
    event.preventDefault();
    var button = form.querySelector("button[type=submit]");
    if (button) button.disabled = true;
    try {
      var response = await fetch(form.action, {method: "POST", body: new FormData(form), headers: {Accept: "application/json"}, credentials: "same-origin"});
      var data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "Setup repair could not finish.");
      var report = data.auto_repair || {};
      var fixed = (report.fixed || []).map(function (item) { return "<li>" + escapeHtml(item) + "</li>"; }).join("");
      var warnings = (report.warnings || []).map(function (item) { return '<li class="text-warning">' + escapeHtml(item) + "</li>"; }).join("");
      var guided = (report.needs_human || []).map(function (step) {
        var fields = (step.fields || []).map(function (field) {
          var fix = field.cta_url ? '<a class="btn btn-sm btn-outline-primary" href="' + escapeHtml(field.cta_url) + '">Fix ' + escapeHtml(field.label) + '</a>' : "";
          return '<li class="d-flex flex-wrap justify-content-between align-items-center gap-2 py-2"><span><strong>' + escapeHtml(field.label) + '</strong><span class="small text-muted d-block">' + escapeHtml(field.current_value) + '</span></span>' + fix + '</li>';
        }).join("");
        var link = step.cta_url ? '<a class="btn btn-sm btn-primary mt-2" href="' + escapeHtml(step.cta_url) + '">Fix the first issue</a>' : "";
        return '<li class="mb-3"><strong>' + escapeHtml(step.label) + '</strong><div class="small text-muted">' + escapeHtml(step.detail) + '</div>' + (fields ? '<ul class="list-unstyled mt-2 mb-0">' + fields + '</ul>' : '') + link + '</li>';
      }).join("");
      var html = '<p><strong>Health:</strong> ' + Number(report.health_before || 0) + "% → " + Number(report.health_after || 0) + "%</p>";
      if (fixed) html += "<h4 class=h6>Fixed automatically</h4><ul>" + fixed + "</ul>";
      if (warnings) html += "<h4 class=h6>Needs attention</h4><ul>" + warnings + "</ul>";
      if (guided) html += "<h4 class=h6>Your guided next steps</h4><ol>" + guided + "</ol>";
      if (!guided && report.launch_ready) html += "<p class=text-success>Your school is launch ready.</p>";
      var dialog = document.querySelector("[data-rmc-auto-repair-dialog]");
      dialog.querySelector("[data-rmc-auto-repair-result]").innerHTML = html;
      if (dialog.showModal) dialog.showModal(); else dialog.setAttribute("open", "");
    } catch (error) { window.alert(error.message || "Setup repair could not finish."); }
    finally { if (button) button.disabled = false; }
  });
  document.addEventListener("click", function (event) { if (!event.target.closest("[data-rmc-auto-repair-close]")) return; var dialog = event.target.closest("dialog"); if (dialog && dialog.close) dialog.close(); });
  document.addEventListener("pointerdown", function (event) {
    var handle = event.target.closest("[data-rmc-dialog-drag-handle]");
    if (!handle || event.target.closest("button, a, input, select, textarea")) return;
    var dialog = handle.closest("dialog");
    if (!dialog) return;
    var rect = dialog.getBoundingClientRect();
    var offsetX = event.clientX - rect.left, offsetY = event.clientY - rect.top;
    dialog.style.position = "fixed"; dialog.style.margin = "0"; dialog.style.left = rect.left + "px"; dialog.style.top = rect.top + "px";
    handle.setPointerCapture(event.pointerId);
    function move(moveEvent) {
      var left = Math.max(0, Math.min(window.innerWidth - dialog.offsetWidth, moveEvent.clientX - offsetX));
      var top = Math.max(0, Math.min(window.innerHeight - dialog.offsetHeight, moveEvent.clientY - offsetY));
      dialog.style.left = left + "px"; dialog.style.top = top + "px";
    }
    function stop() { handle.removeEventListener("pointermove", move); handle.removeEventListener("pointerup", stop); handle.removeEventListener("pointercancel", stop); }
    handle.addEventListener("pointermove", move); handle.addEventListener("pointerup", stop); handle.addEventListener("pointercancel", stop);
  });
})();
