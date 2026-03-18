(function () {
  var root = document.querySelector('[data-mkt-live-flow]');
  if (!root) return;
  var stages = ['admission', 'roster', 'ledger'];
  var panels = root.querySelectorAll('.mkt-live-stage');
  var navItems = root.querySelectorAll('.mkt-live-nav-item');
  var tabs = root.querySelectorAll('.mkt-live-tabs button');

  function show(stage) {
    panels.forEach(function (p) {
      var on = p.getAttribute('data-stage') === stage;
      p.classList.toggle('d-none', !on);
    });
    navItems.forEach(function (n) {
      n.classList.toggle('is-active', n.getAttribute('data-goto') === stage);
    });
    tabs.forEach(function (t) {
      t.classList.toggle('is-active', t.getAttribute('data-goto') === stage);
    });
  }

  function bind(nodes) {
    nodes.forEach(function (el) {
      el.addEventListener('click', function () {
        show(el.getAttribute('data-goto'));
      });
    });
  }
  bind(navItems);
  bind(tabs);

  root.querySelectorAll('.mkt-live-demo-sidebar .mkt-live-nav-item').forEach(function (item) {
    item.addEventListener('mouseenter', function () {
      show(item.getAttribute('data-goto'));
    });
  });
})();
