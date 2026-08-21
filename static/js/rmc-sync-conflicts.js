/* Sync conflicts — bulk resolution wiring.
 *
 * Moved here from rmc-sync-center.js when the conflict queue got its own page. It was
 * always a conflicts concern: it binds to #sync-conflicts-table, which no longer exists
 * on the Sync Center, so leaving it there meant loading and running dead code on every
 * visit to a page that has no table to bind to.
 *
 * The bulk endpoint is unchanged, and so is its contract: POST ids + resolution, reload on
 * success, and on refusal show the server's own message rather than a generic failure —
 * "3 of these are cloud-authoritative" is actionable, "Could not resolve conflicts" is not.
 */
(function () {
  "use strict";

  var host = document.querySelector("[data-rmc-sync-conflicts]");
  var table = document.getElementById("sync-conflicts-table");
  if (!host || !table) {
    return;
  }
  var url = host.getAttribute("data-bulk-url");
  if (!url) {
    return;
  }

  table.addEventListener("rmc:bulk-action", function (ev) {
    var detail = ev.detail || {};
    var ids = detail.ids || [];
    var action = detail.action || "";
    if (!ids.length || !action) {
      return;
    }
    var poster = (window.rmcBulkActions && window.rmcBulkActions.postWithCsrf) || null;
    if (!poster) {
      return;
    }
    poster(url, { ids: ids, resolution: action }).then(function (resp) {
      if (resp && resp.ok) {
        window.location.reload();
        return;
      }
      return resp.json().then(function (body) {
        var msg = document.querySelector("[data-rmc-sync-bulk-msg]");
        if (msg) {
          msg.textContent =
            (body && body.message) ||
            host.getAttribute("data-rmc-bulk-error") ||
            "Could not resolve conflicts.";
          msg.classList.remove("d-none");
        }
      });
    });
  });
})();
