(function () {
  "use strict";
  var node = document.getElementById("rmc-conditional-features-config");
  if (!node || !node.textContent) {
    return;
  }
  try {
    window.RMC_CONDITIONAL_FEATURES = JSON.parse(node.textContent);
  } catch (err) {
    window.RMC_CONDITIONAL_FEATURES = [];
  }
})();
