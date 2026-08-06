(function(){
  var pageDataEl=document.getElementById("page-data-portal__faq_detail-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["portal__faq_detail-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
document.addEventListener('DOMContentLoaded', function() {
    const voteBtns = document.querySelectorAll('.vote-btn');
    
    voteBtns.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const faqId = this.dataset.faqId;
            const voteType = this.dataset.vote;
            const url = `(window.__RMC_PAGE_DATA__["portal__faq_detail-1"]||{})["url_kb_faq_vote"]`;
            
            fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]')?.value
                },
                body: JSON.stringify({
                    faq_id: faqId,
                    vote_type: voteType
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.classList.add('active');
                    alert(data.message);
                    location.reload();
                } else {
                    alert('Error: ' + data.message);
                }
            })
            .catch(error => console.error('Error:', error));
        });
    });

    // CSP: was inline onclick="shareThis()".
    document.querySelector('[data-rmc-share-this]')?.addEventListener('click', shareThis);
});

function shareThis() {
    if (navigator.share) {
        navigator.share({
            title: ((window.__RMC_PAGE_DATA__["portal__faq_detail-1"] || {})["var_faq_question"]),
            text: 'Check out this FAQ on our help center',
            url: window.location.href
        });
    } else {
        alert('Copy the URL to share: ' + window.location.href);
    }
}
})();
