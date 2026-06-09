/**
 * Poll provisioning status API while unified state is "provisioning".
 */
(function () {
  "use strict";
  var root = document.querySelector("[data-rmc-provisioning-poll]");
  if (!root) return;
  var api = root.getAttribute("data-rmc-provisioning-api");
  if (!api) return;
  var intervalMs = 8000;

  function poll() {
    fetch(api, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.ok) return;
        if (data.is_active === true) {
          window.location.reload();
          return;
        }
        var state = (data.unified && data.unified.state) || "";
        if (state && state !== "provisioning") {
          window.location.reload();
        }
      })
      .catch(function () {});
  }

  setInterval(poll, intervalMs);
})();
