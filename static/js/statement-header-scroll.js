/**
 * Scroll-aware statement header: on pages with .statement-header--hero,
 * add .is-solid when user scrolls (for solid background + dark logo).
 */
(function () {
  function init() {
    var header = document.querySelector('.statement-header--hero');
    if (!header) return;
    var solidThreshold = 50;
    function update() {
      if (window.scrollY > solidThreshold) {
        header.classList.add('is-solid');
      } else {
        header.classList.remove('is-solid');
      }
    }
    update();
    window.addEventListener('scroll', function () { update(); }, { passive: true });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
