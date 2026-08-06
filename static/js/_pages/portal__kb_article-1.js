(function(){
  var pageDataEl=document.getElementById("page-data-portal__kb_article-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["portal__kb_article-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  var shareModal = document.getElementById('shareModal');
  var shareBtn = document.getElementById('shareArticleBtn');
  var articleUrlInput = document.getElementById('articleUrl');
  if (shareModal && shareBtn) {
    shareModal.addEventListener('shown.bs.modal', function() {
      if (articleUrlInput) {
        articleUrlInput.focus();
        articleUrlInput.select();
      }
    });
    shareModal.addEventListener('hidden.bs.modal', function() {
      shareBtn.focus();
    });
    shareModal.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        var bsModal = bootstrap.Modal.getInstance(shareModal);
        if (bsModal) bsModal.hide();
      }
    });
  }
})();
function copyUrl() {
  var urlEl = document.getElementById('articleUrl');
  if (!urlEl) return;
  urlEl.select();
  urlEl.setSelectionRange(0, 99999);
  try {
    navigator.clipboard.writeText(urlEl.value);
    alert('URL copied to clipboard!');
  } catch (err) {
    document.execCommand('copy');
    alert('URL copied to clipboard!');
  }
}

function shareOn(platform) {
    const url = encodeURIComponent(window.location.href);
    const title = encodeURIComponent(((window.__RMC_PAGE_DATA__["portal__kb_article-1"] || {})["var_article_title"]));
    let shareUrl;
    
    switch(platform) {
        case 'twitter':
            shareUrl = `https://twitter.com/intent/tweet?url=${url}&text=${title}`;
            break;
        case 'facebook':
            shareUrl = `https://www.facebook.com/sharer/sharer.php?u=${url}`;
            break;
        case 'linkedin':
            shareUrl = `https://www.linkedin.com/sharing/share-offsite/?url=${url}`;
            break;
    }
    
    window.open(shareUrl, '_blank', 'width=600,height=400');
}

// CSP: were inline onclick="copyUrl()" / onclick="shareOn('twitter')" etc.
document.querySelector('[data-rmc-copy-url]')?.addEventListener('click', copyUrl);
document.querySelectorAll('[data-rmc-share-on]').forEach(function (b) {
  b.addEventListener('click', function () { shareOn(b.getAttribute('data-rmc-share-on')); });
});
})();
