(function () {
  var mount = document.getElementById("rmc-gallery-graph-mount");
  var el = document.getElementById("rmc-gallery-graph-json");
  if (!mount || !el || !window.RmcPackageDependencyGraph) return;
  try {
    window.RmcPackageDependencyGraph.render(mount, JSON.parse(el.textContent));
  } catch (e) {}
})();
