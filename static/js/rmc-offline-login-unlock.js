(function () {
  "use strict";
  var button = document.querySelector("[data-rmc-local-mode-open]");
  var dialog = document.querySelector("[data-rmc-local-mode-dialog]");
  if (!button || !dialog || !window.RMCOfflineAuthVault) return;
  var sealed = window.RMCOfflineAuthVault.loadSealed();
  button.hidden = !sealed;
  button.addEventListener("click", function () { if (dialog.showModal) dialog.showModal(); });
  dialog.querySelector("form").addEventListener("submit", async function (event) {
    if (!event.submitter || !event.submitter.hasAttribute("data-rmc-local-mode-unlock")) return;
    event.preventDefault();
    var status = dialog.querySelector("[data-rmc-local-mode-status]");
    try {
      var capability = JSON.parse(await window.RMCOfflineAuthVault.openCapability(event.target.elements.pin.value, sealed) || "null");
      var expires = Date.parse(capability && capability.expires_at);
      if (!capability || capability.version !== 1 || capability.school_host !== window.location.host || !Number.isFinite(expires) || expires <= Date.now()) throw new Error("invalid");
      sessionStorage.setItem("rmc_offline_active_capability", JSON.stringify(capability));
      status.textContent = "Local access unlocked. Opening cached school tools…";
      window.location.assign(capability.start_url || "/");
    } catch (error) {
      // An origin that cannot do WebCrypto is not a wrong PIN, and telling someone to
      // "reconnect and enable local access again" when the browser is withholding
      // crypto.subtle over plain HTTP sends them round a loop that cannot terminate.
      status.textContent =
        (error && error.rmcReason && error.message) ||
        "That PIN did not unlock a current capability. Reconnect and enable local access again.";
      if (window.console && console.warn) console.warn("rmc offline unlock failed", error);
    }
  });
})();
