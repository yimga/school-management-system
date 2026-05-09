(function() {
  var footer = document.getElementById('dashboardFooter');
  if (!footer) return;
  var details = footer.querySelectorAll('.footer-details');
  function setMobileAccordion() {
    var isNarrow = window.innerWidth <= 768;
    details.forEach(function(d) {
      if (isNarrow) d.removeAttribute('open');
      else d.setAttribute('open', '');
    });
  }
  if (window.innerWidth <= 768) {
    details.forEach(function(d) { d.removeAttribute('open'); });
  }
  window.addEventListener('resize', setMobileAccordion);
})();
