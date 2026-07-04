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
          var href = link.getAttribute('href');
          iframe.dataset.loaded = '0';
          iframe.src = href;
          var shell = document.querySelector('[data-rmc-live-preview-contract]');
          var status = shell && shell.querySelector('[data-rmc-preview-status]');
          var newTab = shell && shell.querySelector('[data-rmc-preview-new-tab]');
          if (status) status.textContent = 'Rendering live preview';
          if (newTab && href) newTab.href = href;
          setActive(link);
        }
      });
    });
  })();
  
