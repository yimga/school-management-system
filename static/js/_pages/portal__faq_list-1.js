(function(){
  var pageDataEl=document.getElementById("page-data-portal__faq_list-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["portal__faq_list-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
document.addEventListener('DOMContentLoaded', function() {
    const voteBtns = document.querySelectorAll('.vote-btn');
    
    voteBtns.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const faqId = this.dataset.faqId;
            const voteType = this.dataset.vote;
            const url = `(window.__RMC_PAGE_DATA__["portal__faq_list-1"]||{})["url_kb_faq_vote"]`;
            
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
                } else {
                    alert('Error: ' + data.message);
                }
            })
            .catch(error => console.error('Error:', error));
        });
    });
});
})();
