// Knowledge-base route signature — sets a small global so critical-read
// wiring on portal pages knows which KB surface is rendering. Externalised
// from portal_base.html for CSP-friendliness.
(function () {
  var path = window.location.pathname || "";
  var kind = "";
  if (path.indexOf("/kb/article/") !== -1) {
    kind = "kb-article";
  } else if (path.indexOf("/kb/search") !== -1) {
    kind = "kb-search";
  } else if (path.indexOf("/kb/category/") !== -1) {
    kind = "kb-category";
  } else if (path === "/kb" || path === "/kb/") {
    kind = "kb-home";
  } else if (path.indexOf("/kb") === 0) {
    kind = "kb-hub";
  }
  window.SMS_CRITICAL_READ_KB_KIND = kind;
})();
