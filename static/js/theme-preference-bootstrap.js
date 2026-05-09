// Theme preference bootstrap — applies the user's saved theme before paint
// to avoid flash-of-wrong-theme. Externalised from portal_base.html so the
// page is CSP-friendly (no inline executable script).
(function () {
  var KEY = "runmycampus-theme-preference";
  var saved = localStorage.getItem(KEY) || "light";
  var resolved;
  if (saved === "system") {
    resolved = (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches)
      ? "dark"
      : "light";
  } else {
    resolved = (saved === "dark") ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", resolved);
  document.documentElement.setAttribute("data-bs-theme", resolved);
})();
