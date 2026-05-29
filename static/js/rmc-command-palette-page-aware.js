/**
 * rmc-command-palette-page-aware.js — v4.00.28 (2026-05-29)
 *
 * Augmentation layer that runs BEFORE rmc-command-palette.js. It reads
 * data-rmc-page-domain on <html> (set by admin-quickaction.js's page
 * personality auto-detector) and prepends a "Page actions" group to the
 * command palette JSON data block — so when the user hits ⌘K from a
 * Finance page, the palette opens with Finance-specific quick actions
 * at the top: "New invoice", "Outstanding balances", "Payment runs",
 * etc. From a People page, it's "Add student", "Bulk import roster",
 * "Send broadcast", etc.
 *
 * The augmentation is INSERT-ONLY: it does not modify or remove any
 * existing palette items. Honors the OS-grade aesthetic via
 * data-rmc-cmdk-group="page" so the OS-grade CSS can wash the section
 * with an accent stripe.
 */
(function () {
  "use strict";

  var DATA_ID = "rmc-cmdk-data";

  /* Map data-rmc-page-domain -> array of {label, url|action, icon, keywords}.
     Keep each domain's list tight (5-7 items) so the palette stays scannable.
     URLs are best-effort; if a route is not present in this deploy, the
     palette skips it via its url-or-action validation. */
  var DOMAIN_ACTIONS = {
    finance: [
      { label: "New invoice",        url: "/finance/invoices/new/",         icon: "bi-receipt",           keywords: "fee bill charge" },
      { label: "Outstanding balances", url: "/finance/outstanding/",        icon: "bi-cash-coin",         keywords: "owed receivables overdue" },
      { label: "Payment runs",       url: "/finance/payments/",             icon: "bi-bank",              keywords: "transactions ledger" },
      { label: "Fee schedules",      url: "/finance/fee-schedules/",        icon: "bi-calendar3",         keywords: "tuition pricing" },
      { label: "Payroll dashboard",  url: "/payroll/",                      icon: "bi-wallet2",           keywords: "salaries staff payroll" }
    ],
    people: [
      { label: "Add student",        url: "/people/students/new/",          icon: "bi-person-plus",       keywords: "enroll register" },
      { label: "Bulk import roster", url: "/people/students/import/",       icon: "bi-cloud-upload",      keywords: "csv excel upload" },
      { label: "Send broadcast",     url: "/communication/broadcast/new/",  icon: "bi-megaphone",         keywords: "announce message email sms" },
      { label: "Staff directory",    url: "/people/staff/",                 icon: "bi-people",            keywords: "teacher staff" },
      { label: "Parent / guardian list", url: "/people/parents/",           icon: "bi-person-hearts",     keywords: "guardian family" }
    ],
    academic: [
      { label: "Open gradebook",     url: "/evals/teacher/dashboard/",      icon: "bi-table",             keywords: "grades marks" },
      { label: "Curriculum map",     url: "/curriculum/",                   icon: "bi-diagram-3",         keywords: "subjects scope sequence" },
      { label: "New assessment",     url: "/evals/assessments/new/",        icon: "bi-clipboard-check",   keywords: "quiz test exam" },
      { label: "Bulk grade entry",   url: "/evals/teacher/marks/bulk/",     icon: "bi-pencil-square",     keywords: "marks entry" },
      { label: "Class ranking",      url: "/evals/school-ranking/",         icon: "bi-trophy",            keywords: "top performers ranking" }
    ],
    operations: [
      { label: "Mark attendance",    url: "/attendance/take/",              icon: "bi-check2-square",     keywords: "register absent present" },
      { label: "Today's timetable",  url: "/timetable/today/",              icon: "bi-calendar-week",     keywords: "schedule classes periods" },
      { label: "Calendar",           url: "/calendar/",                     icon: "bi-calendar3",         keywords: "events terms" },
      { label: "Substitute teacher", url: "/timetable/substitutes/",        icon: "bi-arrow-repeat",      keywords: "cover sub replacement" },
      { label: "Bell schedule",      url: "/timetable/bells/",              icon: "bi-bell",              keywords: "periods bell ring" }
    ],
    admissions: [
      { label: "New application",    url: "/admissions/applications/new/",  icon: "bi-file-earmark-plus", keywords: "applicant intake" },
      { label: "Lead inbox",         url: "/admissions/leads/",             icon: "bi-inbox",             keywords: "prospects funnel" },
      { label: "Application queue",  url: "/admissions/queue/",             icon: "bi-stack",             keywords: "review status" },
      { label: "Offer letters",      url: "/admissions/offers/",            icon: "bi-envelope-paper",    keywords: "acceptance offer" }
    ],
    comms: [
      { label: "New broadcast",      url: "/communication/broadcast/new/",  icon: "bi-megaphone",         keywords: "announcement email sms" },
      { label: "Inbox (messages)",   url: "/accounts/messages/",            icon: "bi-chat-square-text",  keywords: "dm conversation" },
      { label: "Notifications inbox", url: "/accounts/notifications/",      icon: "bi-bell",              keywords: "alerts" },
      { label: "Templates",          url: "/communication/templates/",      icon: "bi-file-text",         keywords: "snippet boilerplate" }
    ],
    fleet: [
      { label: "Route monitor",      url: "/transport/routes/",             icon: "bi-geo-alt",           keywords: "bus route gps" },
      { label: "Vehicle roster",     url: "/transport/vehicles/",           icon: "bi-truck",             keywords: "fleet vehicles" },
      { label: "Driver schedule",    url: "/transport/drivers/",            icon: "bi-person-badge",      keywords: "driver schedule" }
    ],
    hostel: [
      { label: "Hostel occupancy",   url: "/hostel/occupancy/",             icon: "bi-house-door",        keywords: "rooms beds" },
      { label: "Boarding roster",    url: "/hostel/roster/",                icon: "bi-people-fill",       keywords: "boarders" },
      { label: "Meal plans",         url: "/hostel/meal-plans/",            icon: "bi-cup-hot",           keywords: "cafeteria food" }
    ],
    marketplace: [
      { label: "Browse marketplace", url: "/marketplace/",                  icon: "bi-shop",              keywords: "apps integrations" },
      { label: "Installed apps",     url: "/marketplace/installed/",        icon: "bi-grid-3x3",          keywords: "installed addons" },
      { label: "Connector status",   url: "/marketplace/connectors/",       icon: "bi-plug",              keywords: "integration webhooks" }
    ],
    security: [
      { label: "Security posture",   url: "/accounts/security/",            icon: "bi-shield-check",      keywords: "mfa posture score" },
      { label: "Audit log",          url: "/compliance/audit/",             icon: "bi-journal-text",      keywords: "logs trail" },
      { label: "Access control",     url: "/access/",                       icon: "bi-key",               keywords: "permissions rbac" }
    ],
    admin: [
      { label: "Tenants",            url: "/admin/tenancy/",                icon: "bi-buildings",         keywords: "schools tenants" },
      { label: "Site settings",      url: "/admin/siteconfig/sitesettings/", icon: "bi-sliders",          keywords: "config" },
      { label: "Operator team",      url: "/admin/accounts/",               icon: "bi-people-gear",       keywords: "admin users" }
    ]
  };

  function getDomain() {
    var d = document.documentElement.getAttribute("data-rmc-page-domain");
    if (d) return d;
    var m = document.querySelector('meta[name="rmc-page-domain"]');
    return (m && m.content) ? m.content : "";
  }

  function injectPageActions() {
    var node = document.getElementById(DATA_ID);
    if (!node || !node.textContent) return;
    var data;
    try { data = JSON.parse(node.textContent); } catch (e) { return; }
    if (!data || !Array.isArray(data.groups)) return;

    var domain = getDomain();
    var items = DOMAIN_ACTIONS[domain];
    if (!items || !items.length) return;

    var pageGroup = {
      label: "Page actions · " + domain.toUpperCase(),
      "data-rmc-cmdk-group": "page",
      items: items.map(function (it) {
        return {
          label: it.label,
          url: it.url || null,
          action: it.action || null,
          icon: it.icon || "bi-arrow-right-circle",
          keywords: (it.keywords || "") + " " + domain
        };
      })
    };

    // Avoid double-inject when this script runs twice (e.g. HTMX swap).
    var alreadyHasPageGroup = data.groups.some(function (g) {
      return g && g["data-rmc-cmdk-group"] === "page";
    });
    if (alreadyHasPageGroup) return;

    data.groups.unshift(pageGroup);
    try { node.textContent = JSON.stringify(data); } catch (e) {}
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", injectPageActions);
  } else {
    injectPageActions();
  }
})();
