(function() {
  function slugify(text) {
    return text.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').replace(/-+/g, '-').trim();
  }
  function buildToc() {
    var content = document.getElementById('content');
    var listEl = document.querySelector('.kb-toc-list');
    if (!content || !listEl) return;
    var headings = content.querySelectorAll('h2, h3, h4');
    var fragment = document.createDocumentFragment();
    if (headings.length > 0) {
      headings.forEach(function(h) {
        var id = h.id || slugify(h.textContent) || ('h-' + Math.random().toString(36).slice(2, 10));
        if (!h.id) h.id = id;
        var li = document.createElement('li');
        li.className = 'kb-toc-' + h.tagName.toLowerCase();
        var a = document.createElement('a');
        a.href = '#' + id;
        a.textContent = h.textContent.trim();
        li.appendChild(a);
        fragment.appendChild(li);
      });
    } else {
      var links = [{ href: '#content', text: 'Overview' }];
      if (document.getElementById('attachments')) links.push({ href: '#attachments', text: 'Visuals & Screenshots' });
      links.push({ href: '#comments', text: 'Comments' });
      links.forEach(function(link) {
        var li = document.createElement('li');
        var a = document.createElement('a');
        a.href = link.href;
        a.textContent = link.text;
        li.appendChild(a);
        fragment.appendChild(li);
      });
    }
    listEl.appendChild(fragment);
    initTocScrollHighlight(listEl);
    addCopyLinksToHeadings(content);
  }
  function addCopyLinksToHeadings(content) {
    var headings = content.querySelectorAll('h2, h3, h4');
    headings.forEach(function(h) {
      if (!h.id) return;
      var wrap = document.createElement('span');
      wrap.className = 'kb-heading-wrap';
      h.parentNode.insertBefore(wrap, h);
      wrap.appendChild(h);
      var a = document.createElement('a');
      a.href = '#' + h.id;
      a.className = 'kb-copy-link';
      a.setAttribute('title', 'Copy link to this section');
      a.setAttribute('aria-label', 'Copy link to this section');
      a.textContent = 'Copy link';
      a.addEventListener('click', function(e) {
        e.preventDefault();
        var url = window.location.origin + window.location.pathname + '#' + h.id;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(url).then(function() { a.textContent = 'Copied!'; setTimeout(function() { a.textContent = 'Copy link'; }, 1200); });
        } else {
          var inp = document.createElement('input');
          inp.value = url;
          document.body.appendChild(inp);
          inp.select();
          document.execCommand('copy');
          document.body.removeChild(inp);
          a.textContent = 'Copied!';
          setTimeout(function() { a.textContent = 'Copy link'; }, 1200);
        }
      });
      wrap.appendChild(a);
    });
  }
  function initTocScrollHighlight(listEl) {
    var links = listEl.querySelectorAll('a[href^="#"]');
    if (links.length === 0) return;
    var targets = [];
    links.forEach(function(a) {
      var id = a.getAttribute('href').slice(1);
      var el = document.getElementById(id);
      if (el) targets.push({ id: id, el: el, link: a });
    });
    if (targets.length === 0) return;
    function setActive(id) {
      links.forEach(function(a) { a.classList.remove('active'); });
      var link = listEl.querySelector('a[href="#' + id + '"]');
      if (link) link.classList.add('active');
    }
    function updateActiveFromScroll() {
      var topOffset = 100;
      var current = null;
      targets.forEach(function(t) {
        var rect = t.el.getBoundingClientRect();
        if (rect.top <= topOffset) current = t;
      });
      if (current) setActive(current.id);
    }
    var ticking = false;
    window.addEventListener('scroll', function() {
      if (!ticking) {
        requestAnimationFrame(function() { updateActiveFromScroll(); ticking = false; });
        ticking = true;
      }
    }, { passive: true });
    updateActiveFromScroll();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildToc);
  } else {
    buildToc();
  }
})();
