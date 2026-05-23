(function () {
  "use strict";
  const form = document.getElementById("rmc-infra-offline-form");
  if (!form) return;
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    const fd = new FormData(form);
    const csrf = form.querySelector("[name=csrfmiddlewaretoken]");
    fetch(window.location.pathname.replace(/\/$/, "") + "/save/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf ? csrf.value : "",
      },
      credentials: "include",
      body: JSON.stringify({
        hub_base_url: fd.get("hub_base_url") || "",
        mesh_enabled: !!fd.get("mesh_enabled"),
        max_queue_items: parseInt(fd.get("max_queue_items"), 10) || 500,
      }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          document.dispatchEvent(
            new CustomEvent("rmc:success", { detail: { message: "Offline settings saved." } }),
          );
        }
      });
  });
})();
