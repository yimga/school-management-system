// Generate idempotency key for receipt upload to prevent duplicate on retry
(function() {
  const form = document.getElementById('receipt-upload-form');
  if (form) {
    const input = document.getElementById('idempotency_key');
    if (input && !input.value) {
      input.value = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
      });
    }
  }
})();
(function() {
  var main = document.getElementById('invoice-detail-main-form');
  if (main && window.FormDraftSave) window.FormDraftSave.init(main);
  var rec = document.getElementById('receipt-upload-form');
  if (rec && window.FormDraftSave) window.FormDraftSave.init(rec);
})();
