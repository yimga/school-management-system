#!/usr/bin/env node
/**
 * Real-host Django admin approval-canvas verifier.
 *
 * This intentionally maps the production-shaped manager and tenant hostnames
 * to a local Django server. Host middleware selects different AdminSite
 * instances, so 127.0.0.1 alone is not valid evidence.
 *
 * Required:
 *   RMC_ADMIN_SESSIONID=<authenticated local Django session>
 *
 * Examples:
 *   node scripts/verify_django_admin_real_host_matrix.mjs --width 1440 --height 900 --theme light --screenshots
 *   node scripts/verify_django_admin_real_host_matrix.mjs --width 390 --height 844 --theme dark
 *   node scripts/verify_django_admin_real_host_matrix.mjs --suite specialized --theme light
 */

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ARTIFACT_DIR = path.join(ROOT, "artifacts", "django-admin-canvas-live");
const LOCK = JSON.parse(
  fs.readFileSync(path.join(ROOT, "var", "admin-approval-build-lock.json"), "utf8"),
);

function parseArgs(argv) {
  const out = {
    width: 1440,
    height: 900,
    theme: "light",
    port: 8020,
    timeout: 120_000,
    suite: "core",
    scope: "both",
    only: "",
    models: "",
    operatorUserId: process.env.RMC_ADMIN_OPERATOR_USER_ID || "",
    tenantUserId: process.env.RMC_ADMIN_TENANT_USER_ID || "",
    schoolId: process.env.RMC_ADMIN_SCHOOL_ID || "",
    siteSettingsId: process.env.RMC_ADMIN_SITE_SETTINGS_ID || "",
    screenshots: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--screenshots") out.screenshots = true;
    else if (value === "--width") out.width = Number(argv[++index]);
    else if (value === "--height") out.height = Number(argv[++index]);
    else if (value === "--theme") out.theme = argv[++index];
    else if (value === "--port") out.port = Number(argv[++index]);
    else if (value === "--timeout") out.timeout = Number(argv[++index]);
    else if (value === "--suite") out.suite = argv[++index];
    else if (value === "--scope") out.scope = argv[++index];
    else if (value === "--only") out.only = argv[++index];
    else if (value === "--models") out.models = argv[++index];
    else if (value === "--operator-user-id") out.operatorUserId = argv[++index];
    else if (value === "--tenant-user-id") out.tenantUserId = argv[++index];
    else if (value === "--school-id") out.schoolId = argv[++index];
    else if (value === "--site-settings-id") out.siteSettingsId = argv[++index];
    else throw new Error(`Unknown argument: ${value}`);
  }
  if (!Number.isFinite(out.width) || out.width < 320) throw new Error("Invalid --width");
  if (!Number.isFinite(out.height) || out.height < 480) throw new Error("Invalid --height");
  if (!Number.isFinite(out.timeout) || out.timeout < 10_000) {
    throw new Error("Invalid --timeout");
  }
  if (!["light", "dark"].includes(out.theme)) throw new Error("--theme must be light or dark");
  if (!["core", "specialized"].includes(out.suite)) {
    throw new Error("--suite must be core or specialized");
  }
  if (!["operator", "tenant", "both"].includes(out.scope)) {
    throw new Error("--scope must be operator, tenant, or both");
  }
  return out;
}

const options = parseArgs(process.argv.slice(2));
const sessionId = (process.env.RMC_ADMIN_SESSIONID || "").trim();
const operatorSessionId = (
  process.env.RMC_ADMIN_OPERATOR_SESSIONID || sessionId
).trim();
const tenantSessionId = (
  process.env.RMC_ADMIN_TENANT_SESSIONID || sessionId
).trim();
if (!operatorSessionId || !tenantSessionId) {
  console.error("DJANGO_ADMIN_REAL_HOST_MATRIX_FAIL");
  console.error(
    "  - RMC_ADMIN_SESSIONID or both RMC_ADMIN_OPERATOR_SESSIONID/RMC_ADMIN_TENANT_SESSIONID are required",
  );
  process.exit(2);
}

const HOSTS = {
  operator: `http://manager.runmycampus.com:${options.port}`,
  tenant: `http://demo-school.runmycampus.com:${options.port}`,
};
const HOSTNAMES = new Set(["manager.runmycampus.com", "demo-school.runmycampus.com"]);

const SPECIALIZED_MODELS = [
  ["automation", "migrationrun"],
  ["brand_experience", "themepack"],
  ["compliance", "compliancerule"],
  ["compliance", "consentrecord"],
  ["compliance", "consentrequest"],
  ["compliance", "legaldocument"],
  ["integrations_marketplace", "appinstallation"],
  ["integrations_marketplace", "integration"],
  ["integrations_marketplace", "marketplaceapp"],
  ["integrations_marketplace", "marketplacelisting"],
  ["integrations_marketplace", "scopegrant"],
  ["integrations_marketplace", "serviceintegration"],
  ["metadata", "dynamicfielddefinition"],
  ["metadata", "dynamicfieldvalue"],
  ["global_registries", "educationsystemprofile"],
  ["global_registries", "gradingscaleconfig"],
  ["platform_runtime", "runtimedefaults"],
  ["portal", "announcement"],
  ["portal", "documentcategory"],
  ["portal", "event"],
  ["portal", "faq"],
  ["portal", "faqcategory"],
  ["portal", "kbarticle"],
  ["portal", "kbcategory"],
  ["portal", "portalfeatureitem"],
  ["registries", "countryregistry"],
  ["siteconfig", "dashboarduserpreference"],
  ["siteconfig", "dashboardwidget"],
  ["siteconfig", "featuretoggledefinition"],
  ["siteconfig", "featuretogglestate"],
  ["siteconfig", "reportcardstyle"],
  ["siteconfig", "sitesettings"],
  ["siteconfig", "tenantadmissionnumberpolicy"],
  ["siteconfig", "themepack"],
  ["siteconfig", "tourstep"],
  ["siteconfig", "userpreference"],
];

function normalizePath(url) {
  const parsed = new URL(url);
  return `${parsed.pathname}${parsed.search}`;
}

async function collectDom(page) {
  return page.evaluate(
    ({ expectedBuild, viewportWidth }) => {
      const visible = (element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return (
          rect.width > 0 &&
          rect.height > 0 &&
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          Number(style.opacity || "1") > 0.01
        );
      };
      const workspaceRoot = document.querySelector(
        [
          '[data-rmc-django-workspace="change-list"]',
          '[data-rmc-django-workspace="change-form"]',
          '[data-rmc-django-workspace="app-index"]',
          '[data-rmc-django-workspace="admin-index"]',
          '[data-rmc-django-workspace="guided"]',
          '[data-rmc-django-workspace="object-history"]',
          '[data-rmc-django-workspace="delete-confirm"]',
          '[data-rmc-django-workspace="delete-selected"]',
        ].join(","),
      );
      const layoutGrid =
        (workspaceRoot?.matches(
          '[data-rmc-django-workspace="change-list"], [data-rmc-django-workspace="change-form"]',
        )
          ? workspaceRoot
          : workspaceRoot?.querySelector(":scope > [data-rmc-admin-index-canvas]")) ||
        document.querySelector("[data-rmc-admin-index-canvas]");
      const primaryPanel =
        layoutGrid?.querySelector(
          ":scope > [data-rmc-django-primary-panel], :scope > .rmc-admin-index-main",
        ) || null;
      const layoutRect = layoutGrid?.getBoundingClientRect() || null;
      const primaryRect = primaryPanel?.getBoundingClientRect() || null;
      const layoutTracks = layoutGrid
        ? (getComputedStyle(layoutGrid).gridTemplateColumns.match(/-?\d+(?:\.\d+)?px/g) || []).map(
            (value) => Number.parseFloat(value),
          )
        : [];
      const primaryTrackWidth = layoutTracks[0] || layoutRect?.width || 0;
      const stylesheets = [...document.querySelectorAll('link[rel="stylesheet"]')];
      const stylesheetHrefs = stylesheets.map((element) => element.href);
      const duplicateStylesheets = [
        ...new Set(stylesheetHrefs.filter((href, index) => stylesheetHrefs.indexOf(href) !== index)),
      ];
      const table = document.querySelector("#result_list");
      const tablePanel =
        table?.closest("[data-rmc-django-table-panel], .results, #changelist-form") || null;
      const tableRect = table?.getBoundingClientRect() || null;
      const panelRect = tablePanel?.getBoundingClientRect() || null;
      const tableAncestry = [];
      if (table) {
        let current = table;
        while (current && tableAncestry.length < 18) {
          const rect = current.getBoundingClientRect();
          const style = getComputedStyle(current);
          tableAncestry.push({
            tag: current.tagName,
            id: current.id,
            className: String(current.className || ""),
            width: rect.width,
            display: style.display,
            grid: style.gridTemplateColumns,
            flex: style.flex,
            maxWidth: style.maxWidth,
            overflowX: style.overflowX,
          });
          if (current === primaryPanel) break;
          current = current.parentElement;
        }
      }
      const saveRoot = document.querySelector("[data-rmc-save-compact]");
      const saveToggle = document.querySelector("[data-rmc-save-menu-toggle]");
      const saveMenu = document.querySelector("[data-rmc-save-menu]");
      const rawIconTokens = [
        "add",
        "close",
        "filter_list",
        "menu",
        "more_vert",
        "notifications",
        "search",
        "settings",
      ];
      const rawIcons = [...document.querySelectorAll("body *")]
        .filter((element) => {
          if (element.children.length || !visible(element)) return false;
          const text = (element.textContent || "").trim();
          if (!rawIconTokens.includes(text)) return false;
          const family = getComputedStyle(element).fontFamily || "";
          return !/Material Symbols|Material Icons/i.test(family);
        })
        .map((element) => ({
          text: (element.textContent || "").trim(),
          tag: element.tagName,
          className: String(element.className || ""),
        }));
      const fixedOverlays = [
        ...document.querySelectorAll(
          [
            "[data-cp-context-drawer]",
            ".cp-context-drawer-shell",
            "#rmc-django-preview-drawer",
            ".rmc-mv-preview-drawer",
            "[data-rmc-copilot-rail]",
            "[data-rmc-operator-notebook]",
            "[data-rmc-portal-row-drawer]",
          ].join(","),
        ),
      ]
        .filter((element) => visible(element) && getComputedStyle(element).position === "fixed")
        .map((element) => ({
          id: element.id,
          className: String(element.className || ""),
        }));
      const wideFixedBands = [...document.body.querySelectorAll("body *")]
        .filter((element) => {
          if (
            !visible(element) ||
            element.closest("[data-rmc-shell-header], .rmc-app-shell__header")
          ) {
            return false;
          }
          const rect = element.getBoundingClientRect();
          const position = getComputedStyle(element).position;
          return (
            (position === "fixed" || position === "sticky") &&
            rect.width >= viewportWidth * 0.72 &&
            rect.height >= 3 &&
            rect.height <= 250
          );
        })
        .map((element) => ({
          tag: element.tagName,
          id: element.id,
          className: String(element.className || ""),
          position: getComputedStyle(element).position,
          width: element.getBoundingClientRect().width,
          height: element.getBoundingClientRect().height,
        }));
      const railElements = [...document.querySelectorAll("[data-rmc-django-side-panel]")].filter(
        visible,
      );
      const toolsElements = [...document.querySelectorAll("[data-rmc-django-tools]")].filter(
        visible,
      );
      const internalScrollTraps = [primaryPanel, ...railElements, ...toolsElements]
        .filter(Boolean)
        .filter((element) => {
          const style = getComputedStyle(element);
          return (
            /(auto|scroll)/.test(style.overflowY) &&
            element.scrollHeight > element.clientHeight + 2
          );
        })
        .map((element) => ({
          id: element.id,
          className: String(element.className || ""),
          overflowY: getComputedStyle(element).overflowY,
          clientHeight: element.clientHeight,
          scrollHeight: element.scrollHeight,
        }));
      const visibleCount = (selector) =>
        [...document.querySelectorAll(selector)].filter(visible).length;
      const structuralCounts = {
        shellRoots: document.querySelectorAll(
          '.rmc-app-shell[data-rmc-shell-root="django-admin"]',
        ).length,
        shellHeaders: visibleCount(".rmc-app-shell__header"),
        shellSidebars: visibleCount(".rmc-app-shell__sidebar"),
        indexCanvases: document.querySelectorAll("[data-rmc-admin-index-canvas]").length,
        primaryPanels: layoutGrid
          ? layoutGrid.querySelectorAll(
              ":scope > [data-rmc-django-primary-panel], :scope > .rmc-admin-index-main",
            ).length
          : 0,
        rails: railElements.length,
        tools: toolsElements.length,
        rowDrawers: document.querySelectorAll("[data-rmc-portal-row-drawer]").length,
        breadcrumbs: visibleCount(
          '[aria-label="Breadcrumb"], [aria-label="Breadcrumbs"], nav.breadcrumbs, .breadcrumbs',
        ),
      };
      const interactiveText = [
        ...document.querySelectorAll("a, button, input[type=submit], [role=button]"),
      ]
        .filter(visible)
        .map((element) =>
          (
            element.getAttribute("aria-label") ||
            element.getAttribute("value") ||
            element.textContent ||
            ""
          )
            .trim()
            .replace(/\s+/g, " "),
        )
        .filter(Boolean);
      const toolTitles = [...document.querySelectorAll("[data-rmc-django-tools] [title]")]
        .filter(visible)
        .map((element) =>
          (
            element.getAttribute("aria-label") ||
            element.getAttribute("title") ||
            element.textContent ||
            ""
          )
            .trim()
            .replace(/\s+/g, " "),
        );
      const searchPanel = document.querySelector(".admin-nav-bridge .cp-search-results-panel");
      const formElement = primaryPanel?.querySelector(":scope > form") || null;
      const formBody = primaryPanel?.querySelector("[data-rmc-django-form-body]") || null;
      const actionsSlot = primaryPanel?.querySelector("[data-rmc-django-actions-slot]") || null;
      const formRect = formElement?.getBoundingClientRect() || null;
      const formBodyRect = formBody?.getBoundingClientRect() || null;
      const actionsRect = actionsSlot?.getBoundingClientRect() || null;
      return {
        url: location.href,
        host: location.hostname,
        path: `${location.pathname}${location.search}`,
        title: document.title,
        scope: document.body.classList.contains("admin-manager-shell")
          ? "operator"
          : document.body.classList.contains("admin-premium-shell")
            ? "tenant"
            : "unknown",
        build: document.querySelector('meta[name="rmc-admin-approval-build"]')?.content || "",
        buildMatches: (
          document.querySelector('meta[name="rmc-admin-approval-build"]')?.content || ""
        ) === expectedBuild,
        theme: document.documentElement.getAttribute("data-resolved-theme") || "",
        h1: [...document.querySelectorAll("h1")]
          .filter(visible)
          .map((element) => (element.textContent || "").trim().replace(/\s+/g, " ")),
        pageOverflow: Math.max(0, document.documentElement.scrollWidth - viewportWidth),
        bodyStylesheetLinks: document.body.querySelectorAll('link[rel="stylesheet"]').length,
        stylesheetCount: stylesheets.length,
        stylesheetHrefs,
        duplicateStylesheets,
        workspace: layoutGrid
          ? workspaceRoot?.getAttribute("data-rmc-django-workspace") ||
            layoutGrid.getAttribute("data-rmc-admin-index-canvas") ||
            "present"
          : "",
        grid: layoutGrid ? getComputedStyle(layoutGrid).gridTemplateColumns : "",
        workspaceWidth: layoutRect?.width || 0,
        primary: primaryPanel
          ? {
              width: primaryRect.width,
              trackWidth: primaryTrackWidth,
              fillRatio: primaryRect.width / Math.max(1, primaryTrackWidth),
              left: primaryRect.left,
              right: primaryRect.right,
            }
          : null,
        structure: structuralCounts,
        tools: toolTitles,
        table: table
          ? {
              display: getComputedStyle(table).display,
              layout: getComputedStyle(table).tableLayout,
              width: tableRect.width,
              panelWidth: panelRect?.width || 0,
              primaryWidth: primaryRect?.width || 0,
              panelFillRatio: (panelRect?.width || 0) / Math.max(1, primaryRect?.width || 0),
              tableFillRatio: tableRect.width / Math.max(1, panelRect?.width || 0),
              ancestry: tableAncestry,
              escapesPanel:
                Boolean(panelRect) &&
                (tableRect.left < panelRect.left - 2 || tableRect.right > panelRect.right + 2),
            }
          : null,
        changelistFilter: document.querySelector("#changelist-filter")
          ? (() => {
              const element = document.querySelector("#changelist-filter");
              const rect = element.getBoundingClientRect();
              const style = getComputedStyle(element);
              return {
                visible: visible(element),
                display: style.display,
                position: style.position,
                width: rect.width,
                height: rect.height,
                flex: style.flex,
              };
            })()
          : null,
        save: {
          present: Boolean(saveRoot),
          primary: Boolean(document.querySelector('[data-rmc-save-compact] [name="_save"]')),
          toggle: Boolean(saveToggle),
          menu: Boolean(saveMenu),
          menuVisible: Boolean(saveMenu && visible(saveMenu)),
        },
        formGeometry: formElement
          ? {
              formWidth: formRect.width,
              bodyWidth: formBodyRect?.width || 0,
              actionsWidth: actionsRect?.width || 0,
              primaryWidth: primaryRect?.width || 0,
              formFillRatio: formRect.width / Math.max(1, primaryRect?.width || 0),
              bodyFillRatio: (formBodyRect?.width || 0) / Math.max(1, formRect.width),
              actionsFillRatio:
                (actionsRect?.width || 0) / Math.max(1, primaryRect?.width || 0),
              panelDisplay: getComputedStyle(primaryPanel).display,
              panelGrid: getComputedStyle(primaryPanel).gridTemplateColumns,
            }
          : null,
        tenantSearchPanelInitiallyVisible: Boolean(searchPanel && visible(searchPanel)),
        fixedOverlays,
        wideFixedBands,
        internalScrollTraps,
        rawIcons,
        interactiveText,
        loginVisible:
          document.body.classList.contains("login") ||
          /\/(?:admin\/)?login\/?$/.test(location.pathname),
      };
    },
    { expectedBuild: LOCK.build_id, viewportWidth: options.width },
  );
}

function gridTracks(grid) {
  return (grid.match(/-?\d+(?:\.\d+)?px/g) || []).map((value) => Number.parseFloat(value));
}

function expectedHost(scope) {
  return scope === "operator" ? "manager.runmycampus.com" : "demo-school.runmycampus.com";
}

function auditResult(result, surface) {
  const findings = [];
  const { dom } = result;
  const expect = (condition, code, detail = "") => {
    if (!condition) findings.push({ code, detail });
  };
  expect(result.status === 200, "http_status", String(result.status));
  expect(result.badResources.length === 0, "bad_resources", JSON.stringify(result.badResources));
  expect(
    result.failedResources.length === 0,
    "failed_resources",
    JSON.stringify(result.failedResources),
  );
  expect(dom.host === expectedHost(surface.scope), "wrong_host", dom.host);
  expect(dom.scope === surface.scope, "wrong_scope", dom.scope);
  expect(!dom.loginVisible, "login_redirect");
  expect(dom.buildMatches, "build_mismatch", dom.build);
  expect(dom.theme === options.theme, "theme_mismatch", dom.theme);
  expect(dom.h1.length === 1, "visible_h1_count", JSON.stringify(dom.h1));
  expect(dom.pageOverflow <= 1, "page_overflow", String(dom.pageOverflow));
  expect(dom.bodyStylesheetLinks === 0, "stylesheet_link_in_body", String(dom.bodyStylesheetLinks));
  expect(
    dom.duplicateStylesheets.length === 0,
    "duplicate_stylesheets",
    JSON.stringify(dom.duplicateStylesheets),
  );
  expect(dom.fixedOverlays.length === 0, "fixed_overlays", JSON.stringify(dom.fixedOverlays));
  expect(
    dom.wideFixedBands.length === 0,
    "unexpected_wide_fixed_or_sticky_band",
    JSON.stringify(dom.wideFixedBands),
  );
  expect(
    dom.internalScrollTraps.length === 0,
    "workspace_internal_vertical_scroll",
    JSON.stringify(dom.internalScrollTraps),
  );
  expect(dom.rawIcons.length === 0, "raw_icon_names", JSON.stringify(dom.rawIcons));
  expect(result.consoleErrors.length === 0, "console_errors", JSON.stringify(result.consoleErrors));
  expect(dom.structure.shellRoots === 1, "shell_root_count", String(dom.structure.shellRoots));
  expect(dom.structure.shellHeaders === 1, "shell_header_count", String(dom.structure.shellHeaders));
  expect(dom.structure.shellSidebars <= 1, "shell_sidebar_count", String(dom.structure.shellSidebars));
  expect(dom.structure.indexCanvases <= 1, "nested_or_duplicate_index_canvas", String(dom.structure.indexCanvases));
  expect(dom.structure.rails <= 1, "context_rail_count", String(dom.structure.rails));
  expect(dom.structure.tools <= 1, "tool_strip_count", String(dom.structure.tools));
  expect(dom.structure.rowDrawers === 0, "unexpected_row_detail_drawer", String(dom.structure.rowDrawers));
  expect(dom.structure.breadcrumbs <= 1, "breadcrumb_count", String(dom.structure.breadcrumbs));

  if (surface.exactPath !== false) {
    expect(normalizePath(dom.url) === normalizePath(surface.url), "unexpected_redirect", dom.url);
  }

  if (surface.workspace) {
    expect(Boolean(dom.workspace), "workspace_missing");
    expect(dom.structure.primaryPanels === 1, "primary_panel_count", String(dom.structure.primaryPanels));
    expect(dom.structure.rails === 1, "page_aware_rail_missing", String(dom.structure.rails));
    expect(dom.structure.tools === 1, "page_aware_tools_missing", String(dom.structure.tools));
    expect(Boolean(dom.primary), "primary_panel_geometry_missing");
    if (dom.primary) {
      expect(
        dom.primary.fillRatio >= 0.94 && dom.primary.fillRatio <= 1.03,
        "primary_track_not_full_fill",
        JSON.stringify(dom.primary),
      );
    }
    const tracks = gridTracks(dom.grid);
    if (options.width <= 1024) {
      expect(tracks.length === 1, "responsive_grid_not_single_column", dom.grid);
    } else {
      expect(tracks.length === 3, "desktop_grid_not_three_columns", dom.grid);
      if (tracks.length === 3) {
        expect(tracks[2] >= 34 && tracks[2] <= 42, "tools_track_width", dom.grid);
        const railShare = tracks[1] / Math.max(1, tracks[0] + tracks[1] + tracks[2]);
        const low = surface.scope === "tenant" ? 0.15 : 0.14;
        const high = surface.scope === "tenant" ? 0.22 : 0.21;
        expect(railShare >= low && railShare <= high, "rail_share", `${railShare}:${dom.grid}`);
      }
    }
  }

  if (surface.kind === "list" && dom.table) {
    expect(dom.table.display === "table", "native_table_display", dom.table.display);
    expect(dom.table.layout === "fixed", "native_table_layout", dom.table.layout);
    expect(!dom.table.escapesPanel, "table_escapes_panel", JSON.stringify(dom.table));
    expect(
      dom.table.panelFillRatio >= 0.9,
      "table_panel_not_full_fill",
      JSON.stringify(dom.table),
    );
    expect(
      dom.table.tableFillRatio >= 0.9,
      "native_table_not_full_fill",
      JSON.stringify(dom.table),
    );
    expect(!dom.tools.some((title) => /view site/i.test(title)), "view_site_on_list");
  }
  if (surface.kind === "form") {
    expect(!dom.tools.some((title) => /filter/i.test(title)), "filters_on_form");
    expect(Boolean(dom.formGeometry), "form_geometry_missing");
    if (dom.formGeometry) {
      expect(
        dom.formGeometry.formFillRatio >= 0.9,
        "form_not_full_fill",
        JSON.stringify(dom.formGeometry),
      );
      expect(
        dom.formGeometry.bodyFillRatio >= 0.94,
        "form_body_not_full_fill",
        JSON.stringify(dom.formGeometry),
      );
      expect(
        dom.formGeometry.actionsFillRatio >= 0.9,
        "save_actions_not_full_fill",
        JSON.stringify(dom.formGeometry),
      );
      expect(
        dom.formGeometry.panelDisplay !== "grid" && dom.formGeometry.panelDisplay !== "inline-grid",
        "form_panel_still_split_grid",
        JSON.stringify(dom.formGeometry),
      );
    }
    if (surface.expectSave !== false) {
      expect(dom.save.present, "compact_save_missing");
      expect(dom.save.primary, "save_primary_missing");
      expect(dom.save.toggle, "save_split_toggle_missing");
      expect(dom.save.menu, "save_split_menu_missing");
      expect(dom.save.menuOperable, "save_split_menu_not_operable");
      expect(dom.save.menuClosesOnEscape, "save_split_menu_escape_broken");
    }
  }
  if (["index", "app-index"].includes(surface.kind)) {
    expect(
      !dom.tools.some((title) => /^(add|filters|view site)/i.test(title)),
      "crud_tool_on_index",
      JSON.stringify(dom.tools),
    );
  }

  if (surface.scope === "tenant") {
    const leaks = dom.interactiveText.filter((text) =>
      /(?:invite (?:a )?school|open studio|studio os|fleet)/i.test(text),
    );
    expect(leaks.length === 0, "tenant_operator_control_leak", JSON.stringify(leaks));
    expect(!dom.tenantSearchPanelInitiallyVisible, "tenant_search_panel_open_empty");
  } else if (surface.kind !== "index") {
    const fleetCtas = dom.interactiveText.filter((text) =>
      /^(?:invite a school|open studio|signup verifications)$/i.test(text),
    );
    expect(fleetCtas.length === 0, "operator_fleet_cta_off_index", JSON.stringify(fleetCtas));
  }

  return findings;
}

function isIgnorableConsoleError(text) {
  return (
    /Cross-Origin-Opener-Policy header has been ignored/i.test(text) ||
    /Failed to load resource.*fonts\.googleapis/i.test(text)
  );
}

async function probe(page, surface) {
  const badResources = [];
  const failedResources = [];
  const consoleErrors = [];
  const documentResponses = [];
  const responseListener = (response) => {
    const request = response.request();
    const resourceType = request.resourceType();
    if (response.request().resourceType() === "document") {
      documentResponses.push(response);
    }
    const redirectLocation = response.headers().location || "";
    if (
      resourceType !== "document" &&
      response.status() >= 300 &&
      response.status() < 400 &&
      /\/authentication\/(?:login|mfa\/)/i.test(redirectLocation)
    ) {
      badResources.push({
        status: response.status(),
        type: resourceType,
        url: response.url(),
        reason: `unexpected background auth redirect to ${redirectLocation}`,
      });
    }
    if (response.status() < 400) return;
    try {
      if (
        HOSTNAMES.has(new URL(response.url()).hostname) ||
        ["127.0.0.1", "localhost"].includes(new URL(response.url()).hostname)
      ) {
        badResources.push({
          status: response.status(),
          type: resourceType,
          url: response.url(),
        });
      }
    } catch {
      // Ignore malformed third-party URLs.
    }
  };
  const consoleListener = (message) => {
    if (message.type() === "error" && !isIgnorableConsoleError(message.text())) {
      const location = message.location();
      consoleErrors.push(
        location?.url ? `${message.text()} @ ${location.url}:${location.lineNumber || 0}` : message.text(),
      );
    }
  };
  const requestFailedListener = (request) => {
    const failure = request.failure()?.errorText || "request failed";
    if (/ERR_ABORTED/i.test(failure)) return;
    failedResources.push({
      type: request.resourceType(),
      url: request.url(),
      error: failure,
    });
  };
  page.on("response", responseListener);
  page.on("console", consoleListener);
  page.on("requestfailed", requestFailedListener);
  let response = null;
  let navigationError = "";
  try {
    response = await page.goto(surface.url, {
      waitUntil: "domcontentloaded",
      timeout: options.timeout,
    });
    await page.waitForTimeout(350);
    if (surface.kind === "delete-selected") {
      const selected = page.locator('input[name="_selected_action"]').first();
      const action = page.locator('select[name="action"]');
      const submit = page.locator('button[name="index"], input[name="index"]').first();
      if ((await selected.count()) && (await action.count()) && (await submit.count())) {
        // Production correctly emits Secure CSRF cookies, which Chromium will
        // not retain on this verifier's local HTTP origin. Seed the host-scoped
        // cookie from Django's rendered token so the non-destructive action
        // probe can reach the real delete-selected confirmation template.
        const csrfToken = await page
          .locator('input[name="csrfmiddlewaretoken"]')
          .first()
          .inputValue();
        await page.context().addCookies([
          {
            name: surface.scope === "operator" ? "rmc_manager_csrftoken" : "csrftoken",
            value: csrfToken,
            domain: new URL(surface.url).hostname,
            path: "/",
            sameSite: "Lax",
          },
        ]);
        await selected.check();
        await action.selectOption("delete_selected");
        const navigation = page
          .waitForNavigation({
            waitUntil: "domcontentloaded",
            timeout: options.timeout,
          })
          .catch(() => null);
        await submit.click();
        const navigationResponse = await navigation;
        response =
          navigationResponse ||
          [...documentResponses]
            .reverse()
            .find((candidate) => candidate.request().method() === "POST") ||
          response;
        await page.waitForLoadState("domcontentloaded", {
          timeout: options.timeout,
        }).catch(() => {});
        await page.waitForTimeout(250);
      } else {
        navigationError = "delete-selected controls are unavailable";
      }
    }
  } catch (error) {
    navigationError = String(error);
  }
  const dom = navigationError
    ? {
        url: page.url(),
        host: "",
        path: "",
        title: "",
        scope: "unknown",
        build: "",
        buildMatches: false,
        theme: "",
        h1: [],
        pageOverflow: 0,
        bodyStylesheetLinks: 0,
        duplicateStylesheets: [],
        workspace: "",
        grid: "",
        primary: null,
        structure: {
          shellRoots: 0,
          shellHeaders: 0,
          shellSidebars: 0,
          indexCanvases: 0,
          primaryPanels: 0,
          rails: 0,
          tools: 0,
          rowDrawers: 0,
          breadcrumbs: 0,
        },
        tools: [],
        table: null,
        save: {},
        formGeometry: null,
        tenantSearchPanelInitiallyVisible: false,
        fixedOverlays: [],
        wideFixedBands: [],
        internalScrollTraps: [],
        rawIcons: [],
        interactiveText: [],
        loginVisible: false,
      }
    : await collectDom(page);
  if (!navigationError && surface.kind === "form" && dom.save?.toggle) {
    const saveToggle = page.locator("[data-rmc-save-menu-toggle]").first();
    await saveToggle.click();
    await page.waitForTimeout(75);
    dom.save.menuOperable = await page
      .locator("[data-rmc-save-menu]")
      .first()
      .evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.display !== "none";
      });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(75);
    dom.save.menuClosesOnEscape = await page
      .locator("[data-rmc-save-menu]")
      .first()
      .evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return (
          element.hidden ||
          rect.width === 0 ||
          rect.height === 0 ||
          style.display === "none" ||
          style.visibility === "hidden"
        );
      });
  }
  const result = {
    name: surface.name,
    scope: surface.scope,
    kind: surface.kind,
    requestedUrl: surface.url,
    status: response?.status() || 0,
    navigationError,
    badResources,
    failedResources,
    consoleErrors,
    dom,
    findings: [],
  };
  if (navigationError) result.findings.push({ code: "navigation_error", detail: navigationError });
  result.findings.push(...auditResult(result, surface));

  if (
    options.screenshots &&
    surface.screenshot &&
    !navigationError &&
    response?.status() === 200
  ) {
    const filename = [
      LOCK.build_id,
      options.suite,
      options.theme,
      String(options.width),
      surface.name,
    ]
      .join("-")
      .replace(/[^a-z0-9_.-]+/gi, "-")
      .toLowerCase();
    const destination = path.join(ARTIFACT_DIR, `${filename}.png`);
    if (surface.kind === "form" && dom.save?.present) {
      const saveDestination = path.join(ARTIFACT_DIR, `${filename}-save-actions.png`);
      await page.screenshot({ path: saveDestination, fullPage: true });
      result.saveActionsScreenshot = path.relative(ROOT, saveDestination).replaceAll("\\", "/");
    }
    await page.evaluate(() => {
      document
        .querySelectorAll(
          ".rmc-app-shell__canvas, .rmc-app-shell__canvas-body, .rmc-shell-canvas-container",
        )
        .forEach((element) => {
          element.scrollTop = 0;
          element.scrollLeft = 0;
        });
      window.scrollTo(0, 0);
    });
    await page.waitForTimeout(75);
    await page.screenshot({ path: destination, fullPage: true });
    result.screenshot = path.relative(ROOT, destination).replaceAll("\\", "/");
  }
  page.off("response", responseListener);
  page.off("console", consoleListener);
  page.off("requestfailed", requestFailedListener);
  return result;
}

async function findFirstChangeUrl(page, base, listPath) {
  await page.goto(`${base}${listPath}`, {
    waitUntil: "domcontentloaded",
    timeout: options.timeout,
  });
  await page.waitForTimeout(250);
  if (new URL(page.url()).pathname !== listPath) return "";
  return page.evaluate(() => {
    const link = [...document.querySelectorAll('a[href$="/change/"]')].find((element) =>
      /^https?:/.test(element.href),
    );
    return link?.href || "";
  });
}

async function discoverCoreSurfaces(page) {
  const surfaces = [];
  const requested = new Set(
    options.only
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
  );
  const wanted = (name) => !requested.size || requested.has(name);
  const add = (name, scope, kind, pathName, extra = {}) => {
    if (!wanted(name)) return;
    surfaces.push({
      name,
      scope,
      kind,
      url: `${HOSTS[scope]}${pathName}`,
      workspace: ["index", "app-index", "list", "form", "guided"].includes(kind),
      ...extra,
    });
  };

  if (options.scope !== "tenant") {
    const operatorNeedsUser = [
      "operator-user-change",
      "operator-user-history",
      "operator-user-delete",
    ].some(wanted);
    const operatorUserChange = operatorNeedsUser
      ? options.operatorUserId
        ? `${HOSTS.operator}/admin/accounts/user/${encodeURIComponent(options.operatorUserId)}/change/`
        : await findFirstChangeUrl(page, HOSTS.operator, "/admin/accounts/user/")
      : "";
    if (operatorNeedsUser && !operatorUserChange) {
      throw new Error("Could not discover an operator user record");
    }
    const operatorUserBase = operatorUserChange
      ? new URL(operatorUserChange).pathname.replace(/change\/$/, "")
      : "";
    add("operator-index", "operator", "index", "/admin/", { screenshot: true });
    add("operator-app-index", "operator", "app-index", "/admin/accounts/", { screenshot: true });
    add("operator-user-list", "operator", "list", "/admin/accounts/user/", { screenshot: true });
    add("operator-user-add", "operator", "form", "/admin/accounts/user/add/", {
      screenshot: true,
    });
    add("operator-user-change", "operator", "form", `${operatorUserBase}change/`, {
      screenshot: true,
    });
    add("operator-user-history", "operator", "history", `${operatorUserBase}history/`);
    add("operator-user-delete", "operator", "delete", `${operatorUserBase}delete/`, {
      screenshot: options.width === 1440,
    });
    add("operator-user-delete-selected", "operator", "delete-selected", "/admin/accounts/user/", {
      screenshot: options.width === 1440,
      exactPath: false,
    });

    const operatorNeedsSchool = [
      "operator-school-change",
      "operator-school-guided-delete",
      "operator-school-waive",
    ].some(wanted);
    const operatorSchoolChange = operatorNeedsSchool
      ? options.schoolId
        ? `${HOSTS.operator}/admin/schools/school/${encodeURIComponent(options.schoolId)}/change/`
        : await findFirstChangeUrl(page, HOSTS.operator, "/admin/schools/school/")
      : "";
    add("operator-schools-list", "operator", "list", "/admin/schools/school/");
    if (operatorSchoolChange) {
      const schoolPath = new URL(operatorSchoolChange).pathname;
      add("operator-school-change", "operator", "form", schoolPath);
      add(
        "operator-school-guided-delete",
        "operator",
        "guided",
        schoolPath.replace(/change\/$/, "delete/"),
        { screenshot: options.width === 1440, expectSave: false },
      );
      const schoolId = schoolPath.split("/").filter(Boolean).at(-2);
      add(
        "operator-school-waive",
        "operator",
        "guided",
        `/admin/schools/school/waive-subscription/?ids=${encodeURIComponent(schoolId)}`,
        { expectSave: false },
      );
    }
    add("operator-country-list", "operator", "list", "/admin/registries/countryregistry/");
    add("operator-runtime-list", "operator", "list", "/admin/platform_runtime/runtimedefaults/");
  }

  if (options.scope !== "operator") {
    const tenantNeedsUser = [
      "tenant-user-change",
      "tenant-user-history",
      "tenant-user-delete",
    ].some(wanted);
    const tenantUserChange = tenantNeedsUser
      ? options.tenantUserId
        ? `${HOSTS.tenant}/admin/accounts/user/${encodeURIComponent(options.tenantUserId)}/change/`
        : await findFirstChangeUrl(page, HOSTS.tenant, "/admin/accounts/user/")
      : "";
    if (tenantNeedsUser && !tenantUserChange) {
      throw new Error("Could not discover a tenant user record");
    }
    const tenantUserBase = tenantUserChange
      ? new URL(tenantUserChange).pathname.replace(/change\/$/, "")
      : "";
    add("tenant-index", "tenant", "index", "/admin/", { screenshot: true });
    add("tenant-app-index", "tenant", "app-index", "/admin/accounts/", { screenshot: true });
    add("tenant-user-list", "tenant", "list", "/admin/accounts/user/", { screenshot: true });
    add("tenant-user-add", "tenant", "form", "/admin/accounts/user/add/", {
      screenshot: true,
    });
    add("tenant-user-change", "tenant", "form", `${tenantUserBase}change/`, {
      screenshot: true,
    });
    add("tenant-user-history", "tenant", "history", `${tenantUserBase}history/`);
    add("tenant-user-delete", "tenant", "delete", `${tenantUserBase}delete/`, {
      screenshot: options.width === 1440,
    });
    add("tenant-user-delete-selected", "tenant", "delete-selected", "/admin/accounts/user/", {
      screenshot: options.width === 1440,
      exactPath: false,
    });

    const tenantNeedsSettings = wanted("tenant-site-settings-change");
    const tenantSettingsChange = tenantNeedsSettings
      ? options.siteSettingsId
        ? `${HOSTS.tenant}/admin/siteconfig/sitesettings/${encodeURIComponent(options.siteSettingsId)}/change/`
        : await findFirstChangeUrl(page, HOSTS.tenant, "/admin/siteconfig/sitesettings/")
      : "";
    add("tenant-site-settings-list", "tenant", "list", "/admin/siteconfig/sitesettings/");
    if (tenantSettingsChange) {
      add(
        "tenant-site-settings-change",
        "tenant",
        "form",
        new URL(tenantSettingsChange).pathname,
        { screenshot: options.width === 1440 },
      );
    }
    add(
      "tenant-global-registry-list",
      "tenant",
      "list",
      "/admin/global_registries/gradingscaleconfig/",
    );
    add(
      "tenant-theme-pack-list",
      "tenant",
      "list",
      "/admin/brand_experience/themepack/",
    );
  }
  return surfaces;
}

async function discoverSpecializedSurfaces(page) {
  const surfaces = [];
  const skipped = [];
  const scopes =
    options.scope === "both" ? ["operator", "tenant"] : [options.scope];
  const requestedModels = new Set(
    options.models
      .split(",")
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean),
  );
  for (const scope of scopes) {
    for (const [appLabel, modelName] of SPECIALIZED_MODELS) {
      if (
        requestedModels.size &&
        !requestedModels.has(`${appLabel}.${modelName}`.toLowerCase())
      ) {
        continue;
      }
      const listPath = `/admin/${appLabel}/${modelName}/`;
      let response;
      try {
        response = await page.goto(`${HOSTS[scope]}${listPath}`, {
          waitUntil: "domcontentloaded",
          timeout: options.timeout,
        });
        await page.waitForTimeout(180);
      } catch (error) {
        skipped.push({ scope, appLabel, modelName, reason: String(error) });
        continue;
      }
      const loginCount = await page.locator('input[name="username"]').count();
      if (
        response?.status() !== 200 ||
        new URL(page.url()).hostname !== expectedHost(scope) ||
        new URL(page.url()).pathname !== listPath ||
        loginCount
      ) {
        skipped.push({
          scope,
          appLabel,
          modelName,
          reason: `not-scoped:${response?.status() || 0}:${page.url()}`,
        });
        continue;
      }
      const target = await page.evaluate(() => {
        const change = [...document.querySelectorAll('a[href$="/change/"]')].find((element) =>
          /^https?:/.test(element.href),
        );
        const add = [...document.querySelectorAll('a[href$="/add/"]')].find((element) =>
          /^https?:/.test(element.href),
        );
        return change?.href || add?.href || "";
      });
      if (!target) {
        skipped.push({ scope, appLabel, modelName, reason: "no-change-or-add-target" });
        continue;
      }
      surfaces.push({
        name: `${scope}-${appLabel}-${modelName}`,
        scope,
        kind: "form",
        url: target,
        workspace: true,
        screenshot:
          ["countryregistry", "runtimedefaults", "sitesettings", "themepack"].includes(modelName),
      });
    }
  }
  return { surfaces, skipped };
}

let activeBrowser = null;

async function main() {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    args: [
      "--host-resolver-rules=MAP manager.runmycampus.com 127.0.0.1, MAP demo-school.runmycampus.com 127.0.0.1",
    ],
  });
  activeBrowser = browser;
  const context = await browser.newContext({
    viewport: { width: options.width, height: options.height },
    colorScheme: options.theme,
    serviceWorkers: "block",
  });
  await context.addInitScript((theme) => {
    localStorage.setItem("runmycampus-theme-preference", theme);
  }, options.theme);
  await context.addCookies(
    [
      ["manager.runmycampus.com", "rmc_manager_sessionid", operatorSessionId],
      ["demo-school.runmycampus.com", "sessionid", tenantSessionId],
    ].map(([domain, name, value]) => ({
      name,
      value,
      domain,
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    })),
  );
  const page = await context.newPage();
  let surfaces;
  let skipped = [];
  if (options.suite === "specialized") {
    const discovery = await discoverSpecializedSurfaces(page);
    surfaces = discovery.surfaces;
    skipped = discovery.skipped;
  } else {
    surfaces = await discoverCoreSurfaces(page);
  }

  const results = [];
  for (const surface of surfaces) {
    const result = await probe(page, surface);
    results.push(result);
    const state = result.findings.length ? "FAIL" : "PASS";
    console.log(
      `${state} ${surface.name} status=${result.status} grid=${JSON.stringify(result.dom.grid)} overflow=${result.dom.pageOverflow}`,
    );
  }
  await browser.close();
  activeBrowser = null;

  const findings = results.flatMap((result) =>
    result.findings.map((finding) => ({ surface: result.name, ...finding })),
  );
  const report = {
    generatedAt: new Date().toISOString(),
    suite: options.suite,
    scope: options.scope,
    only: options.only || null,
    models: options.models || null,
    theme: options.theme,
    viewport: { width: options.width, height: options.height },
    build: LOCK.build_id,
    cacheBust: LOCK.cache_bust,
    serviceWorker: LOCK.sw_version,
    hosts: HOSTS,
    pass: findings.length === 0,
    surfaceCount: results.length,
    skipped,
    findings,
    results,
  };
  const artifactSlug = (value) => {
    if (!value) return "";
    const normalized = value.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "");
    if (normalized.length <= 140) return `-${normalized}`;
    const digest = createHash("sha256").update(normalized).digest("hex").slice(0, 10);
    return `-${normalized.slice(0, 129)}-${digest}`;
  };
  const onlySlug = artifactSlug(options.only);
  const modelSlug = artifactSlug(options.models);
  const reportName = `real-host-${options.suite}-${options.scope}-${options.theme}-${options.width}${onlySlug}${modelSlug}.json`;
  const reportPath = path.join(ARTIFACT_DIR, reportName);
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");

  if (findings.length) {
    console.error("DJANGO_ADMIN_REAL_HOST_MATRIX_FAIL");
    console.error(`  report: ${path.relative(ROOT, reportPath)}`);
    for (const finding of findings.slice(0, 30)) {
      console.error(`  - ${finding.surface}: ${finding.code} ${finding.detail || ""}`.trimEnd());
    }
    return 1;
  }
  console.log("DJANGO_ADMIN_REAL_HOST_MATRIX_PASS");
  console.log(`  surfaces=${results.length} skipped=${skipped.length}`);
  console.log(`  report=${path.relative(ROOT, reportPath)}`);
  return 0;
}

main()
  .then((code) => {
    process.exitCode = code;
  })
  .catch(async (error) => {
    if (activeBrowser) {
      await activeBrowser.close().catch(() => {});
      activeBrowser = null;
    }
    console.error("DJANGO_ADMIN_REAL_HOST_MATRIX_FAIL");
    console.error(`  - ${error.stack || error}`);
    process.exitCode = 1;
  });
