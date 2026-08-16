(function () {
  "use strict";
  var pending = null;
  function getDialog() {
    var node = document.querySelector("[data-rmc-offline-enrollment]");
    if (node) return node;
    node = document.createElement("dialog");
    node.setAttribute("data-rmc-offline-enrollment", "");
    node.className = "rmc-offline-enrollment";
    node.innerHTML = '<form method="dialog"><h2>Make this device offline-ready</h2><p>Create a device PIN. It encrypts a short-lived, read-only capability locally and is never sent to the school.</p><label>Device PIN<input name="pin" type="password" inputmode="numeric" minlength="6" maxlength="64" autocomplete="new-password" required></label><label>Confirm PIN<input name="confirm" type="password" inputmode="numeric" minlength="6" maxlength="64" autocomplete="new-password" required></label><p data-status role="status" aria-live="polite"></p><div><button value="cancel">Not now</button><button value="default" data-enroll>Enable local access</button></div></form>';
    document.body.appendChild(node);
    node.querySelector("form").addEventListener("submit", async function (event) {
      if (!event.submitter || !event.submitter.hasAttribute("data-enroll")) return;
      event.preventDefault();
      var pin = event.target.elements.pin.value;
      var status = node.querySelector("[data-status]");
      if (!pending || pin.length < 6 || pin !== event.target.elements.confirm.value) {
        status.textContent = "Use at least 6 characters and enter the same PIN twice.";
        return;
      }
      try {
        window.RMCOfflineAuthVault.saveSealed(await window.RMCOfflineAuthVault.sealCapability(pin, JSON.stringify(pending)));
        pending = null;
        status.textContent = "This device is offline-ready.";
        window.setTimeout(function () { node.close(); }, 700);
      } catch (_error) { status.textContent = "Local access could not be enabled on this browser."; }
    });
    return node;
  }
  window.addEventListener("rmc-offline-capability-minted", function (event) {
    if (!window.RMCOfflineAuthVault || !event.detail || !event.detail.capability_blob) return;
    pending = { version: 1, capability_blob: event.detail.capability_blob, expires_at: event.detail.expires_at || "", permission_bitmap: event.detail.permission_bitmap || [], school_host: window.location.host, start_url: "/" };
    if (!window.RMCOfflineAuthVault.loadSealed()) {
      var node = getDialog();
      if (node.showModal) node.showModal();
    }
  });
})();
