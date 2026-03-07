/**
 * Photo capture for ID/verification uploads.
 * Hooks into the photo upload phone page; replace with full camera/capture implementation as needed.
 */
(function () {
  'use strict';
  if (typeof document === 'undefined' || !document.addEventListener) return;
  document.addEventListener('DOMContentLoaded', function () {
    var captureBtn = document.getElementById('photo-capture-btn') || document.querySelector('[data-photo-capture]');
    if (captureBtn) {
      captureBtn.addEventListener('click', function () {
        var input = document.getElementById('photo-capture-input') || document.querySelector('input[type="file"][accept*="image"]');
        if (input) input.click();
      });
    }
  });
})();
