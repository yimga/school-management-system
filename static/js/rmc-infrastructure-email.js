(function () {
  "use strict";
  const form = document.getElementById("rmc-infra-email-form");
  const probeBtn = document.getElementById("rmc-infra-email-probe");
  if (!form) return;

  function payloadFromForm() {
    const fd = new FormData(form);
    return {
      enabled: !!fd.get("enabled"),
      host: fd.get("host") || "",
      port: parseInt(fd.get("port"), 10) || 587,
      use_tls: !!fd.get("use_tls"),
      host_user: fd.get("host_user") || "",
      host_password: fd.get("host_password") || "",
      default_from_email: fd.get("default_from_email") || "",
    };
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    const csrf = form.querySelector("[name=csrfmiddlewaretoken]");
    fetch(window.location.pathname.replace(/\/$/, "") + "/save/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf ? csrf.value : "",
      },
      credentials: "include",
      body: JSON.stringify(payloadFromForm()),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          document.dispatchEvent(
            new CustomEvent("rmc:success", { detail: { message: "Email settings saved." } }),
          );
        }
      });
  });

  if (probeBtn) {
    probeBtn.addEventListener("click", function () {
      const csrf = form.querySelector("[name=csrfmiddlewaretoken]");
      fetch(window.location.pathname.replace(/\/$/, "") + "/probe/", {
        method: "POST",
        headers: { "X-CSRFToken": csrf ? csrf.value : "" },
        credentials: "include",
      })
        .then((r) => r.json())
        .then((data) => {
          const ok = !!data.ok;
          document.dispatchEvent(
            new CustomEvent(ok ? "rmc:success" : "rmc:error", {
              detail: { message: ok ? "SMTP probe succeeded." : "SMTP probe failed." },
            }),
          );
        });
    });
  }
})();
