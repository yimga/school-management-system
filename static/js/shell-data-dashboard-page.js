/**
 * Single classifier for data-dashboard-page / body.dashboard-page-* across tenant portal,
 * root base, control-plane skeleton, and Django admin chrome.
 * Keep path rules in this file only; templates load the script, do not duplicate inline logic.
 */
(function () {
  var path = (window.location.pathname || "").toLowerCase();
  var page = "";
  if (path.indexOf("/portal/parent") !== -1 || path.indexOf("/parent/dashboard") !== -1) {
    page = "parent";
  } else if (
    path.indexOf("/portal/teacher") !== -1 ||
    path.indexOf("/teacher/dashboard") !== -1 ||
    path.indexOf("/portal/teacher-dashboard") !== -1 ||
    path.indexOf("/evals/teacher") !== -1
  ) {
    page = "teacher";
  } else if (path.indexOf("/studio/") === 0) {
    page = "studio";
  } else if (path.indexOf("/super/") === 0) {
    page = "super";
  } else if (path.indexOf("/admin/") === 0) {
    page = "django-admin";
  } else if (
    path.indexOf("/accounts/backend") !== -1 ||
    path.indexOf("/accounts/backend-dashboard") !== -1 ||
    path.indexOf("/backend-dashboard") !== -1 ||
    path.indexOf("/authentication/backend") !== -1
  ) {
    page = "backend";
  } else if (path === "/finance" || path.indexOf("/finance/") === 0) {
    page = "finance";
  } else if (path === "/payroll" || path.indexOf("/payroll/") === 0) {
    page = "payroll";
  } else if (path === "/analytics" || path.indexOf("/analytics/") === 0) {
    page = "analytics";
  } else if (path.indexOf("/compliance/dashboard") !== -1) {
    page = "compliance";
  } else if (path === "/requests" || path.indexOf("/requests/") === 0) {
    page = "requests";
  } else if (path === "/emis" || path.indexOf("/emis/") === 0) {
    page = "emis";
  } else if (path.indexOf("/evals/compliance") !== -1) {
    page = "evals-compliance";
  } else if (path.indexOf("/evals/") === 0) {
    page = "evals";
  } else if (
    path.indexOf("/accounts/rbac-dashboard") !== -1 ||
    path.indexOf("/accounts/rbac/") !== -1 ||
    path.indexOf("/authentication/rbac/") !== -1
  ) {
    page = "rbac";
  } else if (path.indexOf("/siteconfig/theme-colors") !== -1 || path.indexOf("/theme-colors") !== -1) {
    page = "theme-colors";
  } else if (path.indexOf("/portal/support/ticket/") !== -1) {
    page = "support-ticket";
  } else if (path.indexOf("/portal/support/hub") !== -1) {
    page = "support-hub";
  } else if (path === "/portal/support" || path === "/portal/support/") {
    page = "support-request";
  } else if (path.indexOf("/kb/article/") !== -1) {
    page = "kb-article";
  } else if (path.indexOf("/kb/search") !== -1) {
    page = "kb-search";
  } else if (path.indexOf("/kb/category/") !== -1) {
    page = "kb-category";
  } else if (path === "/kb" || path === "/kb/") {
    page = "kb-home";
  } else if (path.indexOf("/kb/") === 0) {
    page = "kb-hub";
  } else if (path.indexOf("/organization/network/") !== -1) {
    page = "org-network";
  } else if (path.indexOf("/api-center/") === 0) {
    page = "api-center";
  } else if (path === "/reports" || path.indexOf("/reports/") === 0) {
    page = "reports";
  } else if (path.indexOf("/academics/") === 0) {
    page = "academics";
  } else if (path.indexOf("/automation/") === 0) {
    page = "automation";
  } else if (path.indexOf("/communication/") === 0) {
    page = "communication";
  } else if (path.indexOf("/setup-studio/") === 0 || path.indexOf("/onboard/") === 0) {
    page = "onboarding";
  } else if (path.indexOf("/api/internal/metadata/") === 0 || path.indexOf("/metadata/") === 0) {
    page = "metadata";
  } else if (path.indexOf("/marketplace/") === 0) {
    page = "marketplace";
  } else if (path.indexOf("/siteconfig/") === 0) {
    page = "siteconfig";
  }

  if (!page) {
    return;
  }

  document.documentElement.setAttribute("data-dashboard-page", page);

  var applyBody = function () {
    if (!document.body) {
      return;
    }
    if (!document.body.dataset.dashboardPage) {
      document.body.dataset.dashboardPage = page;
    }
    document.body.classList.add("dashboard-page-" + page);
  };

  applyBody();
  if (!document.body) {
    var observer = new MutationObserver(function () {
      if (document.body) {
        applyBody();
        observer.disconnect();
      }
    });
    observer.observe(document.documentElement, { childList: true });
  }
  document.addEventListener("DOMContentLoaded", applyBody, { once: true });
})();
