(function() {
  var wrap = document.getElementById('control-panel-wrap');
  var iframe = document.getElementById('studio-control-iframe');
  var openFull = document.getElementById('studio-control-open-full');
  var links = document.querySelectorAll('#control-rail-list .control-rail-link');
  var hasPanel = !!document.querySelector('.control-rail-link[data-panel="1"]');
  function syncFullWindowHref() {
    if (!openFull) return;
    if (iframe && iframe.style.display !== 'none' && iframe.src && iframe.src.indexOf('about:blank') !== 0) {
      openFull.setAttribute('href', iframe.src);
      return;
    }
    var active = document.querySelector('#control-rail-list .control-rail-link.active');
    if (active && active.getAttribute('href')) {
      openFull.setAttribute('href', active.getAttribute('href'));
      return;
    }
    var first = document.querySelector('#control-rail-list .control-rail-link');
    if (first && first.getAttribute('href')) {
      openFull.setAttribute('href', first.getAttribute('href'));
    }
  }
  function setActive(el) {
    document.querySelectorAll('#control-rail-list .control-rail-link').forEach(function(l) { l.classList.remove('active'); });
    if (el) el.classList.add('active');
  }
  if (iframe) {
    iframe.addEventListener('load', syncFullWindowHref);
  }
  syncFullWindowHref();
  links.forEach(function(link) {
    link.addEventListener('click', function(e) {
      if (link.getAttribute('data-external') === '1') {
        setActive(link);
        syncFullWindowHref();
        return;
      }
      if (link.getAttribute('data-panel') === '1' && hasPanel) {
        e.preventDefault();
        if (wrap) wrap.style.display = '';
        if (iframe) iframe.style.display = 'none';
        setActive(link);
        syncFullWindowHref();
      } else if (link.getAttribute('data-embed') === '1') {
        e.preventDefault();
        if (iframe) {
          iframe.src = link.getAttribute('href');
          iframe.style.display = 'block';
        }
        if (wrap) wrap.style.display = 'none';
        setActive(link);
        syncFullWindowHref();
      }
    });
  });
})();
