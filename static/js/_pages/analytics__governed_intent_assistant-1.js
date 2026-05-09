(function(){
  var pageDataEl=document.getElementById("page-data-analytics__governed_intent_assistant-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["analytics__governed_intent_assistant-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function(){
  function csrftoken(){ var m=document.cookie.match(/csrftoken=([^;]+)/); return m?m[1]:""; }
  var previewUrl="(window.__RMC_PAGE_DATA__["analytics__governed_intent_assistant-1"]||{})["var_preview_url"]";
  var executeUrl="(window.__RMC_PAGE_DATA__["analytics__governed_intent_assistant-1"]||{})["var_execute_url"]";
  var lastIntent=null;
  document.getElementById("nl-preview").addEventListener("click", function(){
    var t=document.getElementById("nl-text").value||"";
    document.getElementById("nl-status").textContent="";
    fetch(previewUrl,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json","X-CSRFToken":csrftoken()},body:JSON.stringify({text:t})})
      .then(function(r){return r.json();})
      .then(function(j){
        document.getElementById("nl-out").textContent=JSON.stringify(j,null,2);
        lastIntent=j.intent_id||null;
        document.getElementById("nl-run").disabled=!j.supported;
      }).catch(function(e){document.getElementById("nl-status").textContent=String(e);});
  });
  document.getElementById("nl-run").addEventListener("click", function(){
    if(!lastIntent)return;
    fetch(executeUrl,{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/json","X-CSRFToken":csrftoken()},body:JSON.stringify({intent_id:lastIntent,confirm:true})})
      .then(function(r){return r.json();})
      .then(function(j){document.getElementById("nl-out").textContent=JSON.stringify(j,null,2);})
      .catch(function(e){document.getElementById("nl-status").textContent=String(e);});
  });
})();
})();
