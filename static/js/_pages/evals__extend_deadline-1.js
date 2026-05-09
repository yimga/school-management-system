(function(){
  var pageDataEl=document.getElementById("page-data-evals__extend_deadline-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["evals__extend_deadline-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
const currentDeadline = new Date('(window.__RMC_PAGE_DATA__["evals__extend_deadline-1"]||{})["var_deadline_deadline_date_date_c"]');

function updateNewDeadline() {
    const daysExtension = parseInt(document.getElementById('daysExtension').value) || 0;
    const newDate = new Date(currentDeadline);
    newDate.setDate(newDate.getDate() + daysExtension);
    
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    document.getElementById('newDeadline').textContent = newDate.toLocaleDateString('en-US', options);
}

document.getElementById('daysExtension').addEventListener('input', updateNewDeadline);
window.addEventListener('load', updateNewDeadline);
})();
