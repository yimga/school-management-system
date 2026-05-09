(function() {
  function initMermaid() {
    if (typeof mermaid === 'undefined') return;
    mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose' });
    var blocks = document.querySelectorAll('#content pre code.language-mermaid');
    blocks.forEach(function(code) {
      var pre = code.closest('pre');
      var text = (code.textContent || '').trim();
      if (!text) return;
      var id = 'mermaid-' + Math.random().toString(36).slice(2, 10);
      var div = document.createElement('div');
      div.className = 'mermaid';
      div.id = id;
      div.textContent = text;
      pre.parentNode.replaceChild(div, pre);
    });
    if (blocks.length) mermaid.run({ nodes: document.querySelectorAll('#content .mermaid') });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMermaid);
  } else {
    initMermaid();
  }
})();
