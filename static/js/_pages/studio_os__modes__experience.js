  (function() {
    var iframe = document.getElementById('studio-experience-iframe');
    var links = document.querySelectorAll('#experience-rail-list .experience-rail-link');
    function setActive(el) {
      document.querySelectorAll('#experience-rail-list .experience-rail-link').forEach(function(l) { l.classList.remove('active'); });
      if (el) el.classList.add('active');
    }
    links.forEach(function(link) {
      link.addEventListener('click', function(e) {
        if (link.getAttribute('data-external') === '1') {
          setActive(link);
          return;
        }
        if (link.getAttribute('data-embed') === '1' && iframe) {
          e.preventDefault();
          iframe.src = link.getAttribute('href');
          setActive(link);
        }
      });
    });
  })();
  
