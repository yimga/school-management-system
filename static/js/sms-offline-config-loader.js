// SMS_OFFLINE_CONFIG loader — reads its config from a JSON data island
// (<script type="application/json" id="sms-offline-config">) instead of
// being interpolated by Django at template-render time. CSP-friendly.
(function () {
  var el = document.getElementById('sms-offline-config');
  if (!el) {
    window.SMS_OFFLINE_CONFIG = window.SMS_OFFLINE_CONFIG || {};
    return;
  }
  try {
    window.SMS_OFFLINE_CONFIG = JSON.parse(el.textContent || '{}');
  } catch (_e) {
    window.SMS_OFFLINE_CONFIG = {};
  }
})();
