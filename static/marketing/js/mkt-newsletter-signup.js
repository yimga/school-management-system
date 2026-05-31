(function () {
  "use strict";

  function readCookie(name) {
    var match = document.cookie.match(new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()\[\]\\\/\+^])/g, "\\$1") + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : "";
  }

  function showStatus(form, message, ok) {
    var status = form.querySelector("[data-newsletter-status]");
    if (!status) {
      return;
    }
    status.classList.remove("visually-hidden");
    status.textContent = message;
    status.setAttribute("data-state", ok ? "ok" : "error");
  }

  function handleSubmit(event) {
    var form = event.currentTarget;
    if (!form || form.dataset.newsletterBusy === "1") {
      return;
    }
    if (form.getAttribute("target") === "_blank") {
      return;
    }
    var action = form.getAttribute("action") || "";
    if (!action || /^https?:\/\//i.test(action)) {
      return;
    }

    event.preventDefault();
    form.dataset.newsletterBusy = "1";

    var data = new FormData(form);
    var payload = {};
    data.forEach(function (value, key) {
      payload[key] = value;
    });

    var csrf = readCookie("csrftoken");
    fetch(action, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-CSRFToken": csrf,
        "X-Requested-With": "fetch"
      },
      body: JSON.stringify(payload)
    })
      .then(function (response) {
        return response.json().then(function (body) {
          return { status: response.status, body: body };
        });
      })
      .then(function (result) {
        var ok = result && result.body && result.body.ok === true;
        if (ok) {
          showStatus(form, "Check your email to confirm your subscription.", true);
          var emailInput = form.querySelector('input[type="email"]');
          if (emailInput) {
            emailInput.value = "";
          }
        } else {
          var reason = (result && result.body && result.body.reason) || "unknown_error";
          showStatus(form, "We couldn't subscribe you (" + reason + "). Please try again.", false);
        }
      })
      .catch(function () {
        showStatus(form, "Network error. Please try again.", false);
      })
      .then(function () {
        form.dataset.newsletterBusy = "";
      });
  }

  function init() {
    var forms = document.querySelectorAll("form[data-newsletter-form]");
    for (var i = 0; i < forms.length; i++) {
      forms[i].addEventListener("submit", handleSubmit);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
