/**
 * Per-session security posture modal — must dismiss (X) once per browser session.
 */
(function () {
  "use strict";

  function readConfig() {
    var el = document.getElementById("rmc-security-posture-modal-config");
    if (!el || !el.textContent) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  function csrfToken() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input && input.value) return input.value;
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function postAck(url) {
    if (!url) return Promise.resolve();
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": csrfToken(),
        "Content-Type": "application/json",
      },
      body: "{}",
    }).catch(function () {
      return null;
    });
  }

  function wireModal(modalEl, cfg) {
    if (!modalEl || typeof bootstrap === "undefined" || !bootstrap.Modal) return;
    var modal = bootstrap.Modal.getOrCreateInstance(modalEl, {
      backdrop: "static",
      keyboard: false,
    });

    function onDismiss() {
      postAck(cfg && cfg.ack_url);
    }

    modalEl.querySelectorAll("[data-rmc-security-posture-modal-close]").forEach(function (btn) {
      btn.addEventListener("click", onDismiss);
    });
    modalEl.addEventListener("hidden.bs.modal", onDismiss, { once: false });

    if (cfg && cfg.auto_show) {
      window.setTimeout(function () {
        modal.show();
      }, 400);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var modalEl = document.getElementById("rmcSecurityPostureSessionModal");
    if (!modalEl) return;
    wireModal(modalEl, readConfig());
  });
})();
