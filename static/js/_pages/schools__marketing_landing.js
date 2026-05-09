(function () {
  var bar = document.getElementById('mkt-sticky-cta-bar');
  var hero = document.getElementById('hero');
  if (!bar || !hero) return;
  var threshold = 350;
  function update() {
    var show = window.scrollY > threshold;
    bar.classList.toggle('is-visible', show);
    bar.setAttribute('aria-hidden', show ? 'false' : 'true');
  }
  window.addEventListener('scroll', function () { requestAnimationFrame(update); }, { passive: true });
  window.addEventListener('resize', update);
  update();
})();
