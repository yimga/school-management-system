// Studio OS overview deck: digit shortcuts 1–5 jump to mode cards (home only).
(function () {
  var deck = document.querySelector('[data-studio-command-deck="1"]');
  if (!deck) return;

  document.addEventListener('keydown', function (e) {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
    var tag = (e.target && e.target.tagName) || '';
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag)) return;
    if (e.target && e.target.isContentEditable) return;
    var digit = e.key;
    if (!/^[1-5]$/.test(digit)) return;
    var link = deck.querySelector('[data-studio-shortcut="' + digit + '"]');
    if (!link || !link.href) return;
    e.preventDefault();
    window.location.assign(link.href);
  });
})();
