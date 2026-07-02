(function(){
  var pageDataEl=document.getElementById("page-data-partials__language_switcher-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["partials__language_switcher-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}

  // Submit the language choice through set_language_persist (server writes the
  // durable User.preferred_language + session + cookie). One source of truth —
  // no localStorage fork and no manual cookie write on the client.
  function submitLanguage(code){
    var form=document.getElementById("rmc-lang-form");
    var input=document.getElementById("rmc-lang-input");
    if(form&&input){
      input.value=code;
      form.submit();
      return;
    }
    // Fallback if the persist form is unavailable: cookie + reload.
    document.cookie="django_language="+encodeURIComponent(code)+"; path=/; max-age=31536000";
    var url=new URL(window.location);
    url.searchParams.set("language",code);
    window.location.href=url.toString();
  }

  document.addEventListener("click",function(ev){
    var btn=ev.target&&ev.target.closest?ev.target.closest("[data-rmc-lang]"):null;
    if(btn){
      ev.preventDefault();
      submitLanguage(btn.getAttribute("data-rmc-lang"));
    }
  });
})();
