  document.addEventListener('DOMContentLoaded', function () {
    document.addEventListener('keydown', function (e) {
      if (e.key === '/' && !/^(input|textarea|select)$/i.test((e.target || {}).tagName) && !e.ctrlKey && !e.metaKey && !e.altKey) {
        var el = document.getElementById('kb-search-input');
        if (el) { el.focus(); e.preventDefault(); }
      }
    });
  });
