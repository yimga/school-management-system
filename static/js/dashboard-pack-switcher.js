/*
 * Dashboard Packs revival (Phase 4): per-user "Choose your dashboard" switcher.
 *
 * Reads the API endpoint from [data-rmc-dashboard-pack-switcher], PATCHes the chosen
 * DashboardPack.code to api:dashboard-pack-preference, then reloads so the role-home
 * render picks up the new overlay. Preview-before-apply: the radio selection is the
 * preview; nothing is written until "Apply" is clicked. Fails soft (status message,
 * never throws into the page).
 */
(function () {
  "use strict";

  function getCsrfToken() {
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : "";
  }

  function wire(root) {
    var endpoint = root.getAttribute("data-endpoint") || "";
    var form = root.querySelector("[data-rmc-dashboard-pack-form]");
    var status = root.querySelector("[data-rmc-dashboard-pack-status]");
    var applyBtn = root.querySelector("[data-rmc-dashboard-pack-apply]");
    if (!endpoint || !form) {
      return;
    }

    function setStatus(message) {
      if (status) {
        status.textContent = message || "";
      }
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var checked = form.querySelector('input[name="dashboard_pack"]:checked');
      var code = checked ? checked.value : "";
      var current = root.getAttribute("data-selected") || "";
      if (code === current) {
        setStatus("Already applied.");
        return;
      }
      if (applyBtn) {
        applyBtn.setAttribute("disabled", "disabled");
      }
      setStatus("Applying…");

      fetch(endpoint, {
        method: "PATCH",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrfToken(),
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify({ dashboard_pack: code })
      })
        .then(function (resp) {
          if (!resp.ok) {
            throw new Error("HTTP " + resp.status);
          }
          return resp.json();
        })
        .then(function () {
          try {
            localStorage.setItem("rmc-dashboard-pack-applied", code || "__default__");
          } catch (e) { /* ignore quota */ }
          root.classList.add("rmc-dpk--applying");
          if (document.documentElement) {
            document.documentElement.setAttribute("data-rmc-dashboard-pack-applying", "1");
          }
          setStatus("Applied. Refreshing…");
          window.location.reload();
        })
        .catch(function () {
          setStatus("Could not apply. Please try again.");
          if (applyBtn) {
            applyBtn.removeAttribute("disabled");
          }
        });
    });
  }

  function init() {
    var roots = document.querySelectorAll("[data-rmc-dashboard-pack-switcher]");
    for (var i = 0; i < roots.length; i++) {
      wire(roots[i]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
