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
if (!sessionId) {
  console.error("DJANGO_ADMIN_REAL_HOST_MATRIX_FAIL");
  console.error("  - RMC_ADMIN_SESSIONID is required");
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
      const workspace =
        document.querySelector(
          '[data-rmc-django-workspace="guided"] [data-rmc-admin-index-canvas]',
        ) ||
        document.querySelector(
          [
            "[data-rmc-admin-index-canvas]",
            '[data-rmc-django-workspace="change-list"]',
            '[data-rmc-django-workspace="change-form"]',
            '[data-rmc-django-workspace="app-index"] .rmc-admin-index-canvas',
          ].join(","),
        );
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
          ].join(","),
        ),
      ]
        .filter((element) => visible(element) && getComputedStyle(element).position === "fixed")
        .map((element) => ({
          id: element.id,
          className: String(element.className || ""),
        }));
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
        duplicateStylesheets,
        workspace: workspace
          ? workspace.getAttribute("data-rmc-django-workspace") ||
            workspace.getAttribute("data-rmc-admin-index-canvas") ||
            "present"
          : "",
        grid: workspace ? getComputedStyle(workspace).gridTemplateColumns : "",
        workspaceWidth: workspace ? workspace.getBoundingClientRect().width : 0,
        tools: toolTitles,
        table: table
          ? {
              display: getComputedStyle(table).display,
              layout: getComputedStyle(table).tableLayout,
              width: tableRect.width,
              panelWidth: panelRect?.width || 0,
              escapesPanel:
                Boolean(panelRect) &&
                (tableRect.left < panelRect.left - 2 || tableRect.right > panelRect.right + 2),
            }
          : null,
        save: {
          present: Boolean(saveRoot),
          primary: Boolean(document.querySelector('[data-rmc-save-compact] [name="_save"]')),
          toggle: Boolean(saveToggle),
          menu: Boolean(saveMenu),
          menuVisible: Boolean(saveMenu && visible(saveMenu)),
        },
        tenantSearchPanelInitiallyVisible: Boolean(searchPanel && visible(searchPanel)),
        fixedOverlays,
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
  expect(dom.rawIcons.length === 0, "raw_icon_names", JSON.stringify(dom.rawIcons));
  expect(result.consoleErrors.length === 0, "console_errors", JSON.stringify(result.consoleErrors));

  if (surface.exactPath !== false) {
    expect(normalizePath(dom.url) === normalizePath(surface.url), "unexpected_redirect", dom.url);
  }

  if (surface.workspace) {
    expect(Boolean(dom.workspace), "workspace_missing");
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
    expect(!dom.tools.some((title) => /view site/i.test(title)), "view_site_on_list");
  }
  if (surface.kind === "form") {
    expect(!dom.tools.some((title) => /filter/i.test(title)), "filters_on_form");
    if (surface.expectSave !== false) {
      expect(dom.save.present, "compact_save_missing");
      expect(dom.save.primary, "save_primary_missing");
      expect(dom.save.toggle, "save_split_toggle_missing");
      expect(dom.save.menu, "save_split_menu_missing");
      expect(dom.save.menuOperable, "save_split_menu_not_operable");
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
  const consoleErrors = [];
  const documentResponses = [];
  const responseListener = (response) => {
    if (response.request().resourceType() === "document") {
      documentResponses.push(response);
    }
    if (response.status() < 400) return;
    try {
      if (HOSTNAMES.has(new URL(response.url()).hostname)) {
        badResources.push({
          status: response.status(),
          type: response.request().resourceType(),
          url: response.url(),
        });
      }
    } catch {
      // Ignore malformed third-party URLs.
    }
  };
  const consoleListener = (message) => {
    if (message.type() === "error" && !isIgnorableConsoleError(message.text())) {
      consoleErrors.push(message.text());
    }
  };
  page.on("response", responseListener);
  page.on("console", consoleListener);
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
        tools: [],
        table: null,
        save: {},
        tenantSearchPanelInitiallyVisible: false,
        fixedOverlays: [],
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
  }
  const result = {
    name: surface.name,
    scope: surface.scope,
    kind: surface.kind,
    requestedUrl: surface.url,
    status: response?.status() || 0,
    navigationError,
    badResources,
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
    await page.screenshot({ path: destination, fullPage: true });
    result.screenshot = path.relative(ROOT, destination).replaceAll("\\", "/");
  }
  page.off("response", responseListener);
  page.off("console", consoleListener);
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
  const add = (name, scope, kind, pathName, extra = {}) => {
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
    const operatorUserChange = options.operatorUserId
      ? `${HOSTS.operator}/admin/accounts/user/${encodeURIComponent(options.operatorUserId)}/change/`
      : await findFirstChangeUrl(page, HOSTS.operator, "/admin/accounts/user/");
    if (!operatorUserChange) throw new Error("Could not discover an operator user record");
    const operatorUserBase = new URL(operatorUserChange).pathname.replace(/change\/$/, "");
    add("operator-index", "operator", "index", "/admin/", { screenshot: true });
    add("operator-app-index", "operator", "app-index", "/admin/accounts/");
    add("operator-user-list", "operator", "list", "/admin/accounts/user/", { screenshot: true });
    add("operator-user-add", "operator", "form", "/admin/accounts/user/add/", {
      screenshot: true,
    });
    add("operator-user-change", "operator", "form", `${operatorUserBase}change/`);
    add("operator-user-history", "operator", "history", `${operatorUserBase}history/`);
    add("operator-user-delete", "operator", "delete", `${operatorUserBase}delete/`, {
      screenshot: options.width === 1440,
    });
    add("operator-user-delete-selected", "operator", "delete-selected", "/admin/accounts/user/", {
      screenshot: options.width === 1440,
      exactPath: false,
    });

    const operatorSchoolChange = options.schoolId
      ? `${HOSTS.operator}/admin/schools/school/${encodeURIComponent(options.schoolId)}/change/`
      : await findFirstChangeUrl(page, HOSTS.operator, "/admin/schools/school/");
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
    const tenantUserChange = options.tenantUserId
      ? `${HOSTS.tenant}/admin/accounts/user/${encodeURIComponent(options.tenantUserId)}/change/`
      : await findFirstChangeUrl(page, HOSTS.tenant, "/admin/accounts/user/");
    if (!tenantUserChange) throw new Error("Could not discover a tenant user record");
    const tenantUserBase = new URL(tenantUserChange).pathname.replace(/change\/$/, "");
    add("tenant-index", "tenant", "index", "/admin/", { screenshot: true });
    add("tenant-app-index", "tenant", "app-index", "/admin/accounts/");
    add("tenant-user-list", "tenant", "list", "/admin/accounts/user/", { screenshot: true });
    add("tenant-user-add", "tenant", "form", "/admin/accounts/user/add/", {
      screenshot: true,
    });
    add("tenant-user-change", "tenant", "form", `${tenantUserBase}change/`);
    add("tenant-user-history", "tenant", "history", `${tenantUserBase}history/`);
    add("tenant-user-delete", "tenant", "delete", `${tenantUserBase}delete/`, {
      screenshot: options.width === 1440,
    });
    add("tenant-user-delete-selected", "tenant", "delete-selected", "/admin/accounts/user/", {
      screenshot: options.width === 1440,
      exactPath: false,
    });

    const tenantSettingsChange = options.siteSettingsId
      ? `${HOSTS.tenant}/admin/siteconfig/sitesettings/${encodeURIComponent(options.siteSettingsId)}/change/`
      : await findFirstChangeUrl(page, HOSTS.tenant, "/admin/siteconfig/sitesettings/");
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
  if (!options.only) return surfaces;
  const requested = new Set(
    options.only
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean),
  );
  return surfaces.filter((surface) => requested.has(surface.name));
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

async function main() {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    args: [
      "--host-resolver-rules=MAP manager.runmycampus.com 127.0.0.1, MAP demo-school.runmycampus.com 127.0.0.1",
    ],
  });
  const context = await browser.newContext({
    viewport: { width: options.width, height: options.height },
    colorScheme: options.theme,
  });
  await context.addInitScript((theme) => {
    localStorage.setItem("runmycampus-theme-preference", theme);
  }, options.theme);
  await context.addCookies(
    [
      ["manager.runmycampus.com", "rmc_manager_sessionid"],
      ["demo-school.runmycampus.com", "sessionid"],
    ].map(([domain, name]) => ({
      name,
      value: sessionId,
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
  const onlySlug = options.only
    ? `-${options.only.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "")}`
    : "";
  const modelSlug = options.models
    ? `-${options.models.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "")}`
    : "";
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
  .catch((error) => {
    console.error("DJANGO_ADMIN_REAL_HOST_MATRIX_FAIL");
    console.error(`  - ${error.stack || error}`);
    process.exitCode = 1;
  });
