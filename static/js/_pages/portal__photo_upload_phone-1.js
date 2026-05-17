(function(){
  var pageDataEl=document.getElementById("page-data-portal__photo_upload_phone-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["portal__photo_upload_phone-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  var form = document.getElementById('photoUploadForm');
  var uploadSection = document.getElementById('uploadSection');
  var successMessage = document.getElementById('successMessage');
  var errorMessage = document.getElementById('errorMessage');
  var fileInput = document.getElementById('id_photo');

  function checkPhoto() {
    if (fileInput && fileInput.files && fileInput.files.length > 0) {
      uploadSection.style.display = 'block';
    }
  }
  if (fileInput) {
    fileInput.addEventListener('change', checkPhoto);
  }
  setTimeout(checkPhoto, 500);

  form.addEventListener('submit', function(e) {
    e.preventDefault();
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
      errorMessage.textContent = ((window.__RMC_PAGE_DATA__["portal__photo_upload_phone-1"] || {})["trans_please_take_or_choose_a_photo_first"]);
      errorMessage.style.display = 'block';
      return;
    }
    var fd = new FormData(form);
    errorMessage.style.display = 'none';
    fetch(form.action, {
      method: 'POST',
      body: fd,
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(function(r) { return r.json().then(function(d) { return { ok: r.ok, data: d }; }); })
    .then(function(r) {
      if (r.ok) {
        form.style.display = 'none';
        uploadSection.style.display = 'none';
        successMessage.style.display = 'block';
      } else {
        errorMessage.textContent = r.data && r.data.error ? r.data.error : ((window.__RMC_PAGE_DATA__["portal__photo_upload_phone-1"] || {})["trans_upload_failed_try_again"]);
        errorMessage.style.display = 'block';
      }
    })
    .catch(function() {
      errorMessage.textContent = ((window.__RMC_PAGE_DATA__["portal__photo_upload_phone-1"] || {})["trans_upload_failed_check_your_connection_and_try_again"]);
      errorMessage.style.display = 'block';
    });
  });
})();
})();
