#!/usr/bin/env node
/** Real-host browser matrix for the approved tenant configuration operations canvas. */

import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const HOST = (process.env.RMC_TENANT_BROWSER_HOST || "demo-school.runmycampus.com").trim();
const PORT = Number(process.env.RMC_TENANT_BROWSER_PORT || "8031");
const PYTHON = (process.env.RMC_TENANT_BROWSER_PYTHON || "python").trim();
const BUILD_ID = "2026-08-01-v1.0";
const OUTPUT = path.join(
  ROOT,
  "artifacts",
  "design-approvals",
  "gilead-configuration-surface-audit-2026-08-01",
);
const REPORT = path.join(OUTPUT, "post-implementation-browser-matrix.json");
const SERVER_LOG = path.join(OUTPUT, "browser-runserver.log");

const ROUTES = [
  { key: "settings", path: "/school/settings/", build: true },
  { key: "configuration", path: "/school/configuration/", build: true },
  { key: "academics", path: "/academics/", build: true },
  {
    key: "offline-sync-alias",
    path: "/portal/offline-sync/?source=browser-audit",
    finalPath: "/portal/offline/sync-queue/",
    build: true,
  },
  { key: "finance", path: "/finance/", build: true },
  { key: "app-catalog", path: "/settings/app-catalog/", build: true },
  {
    key: "compliance-alias",
    path: "/compliance/?source=browser-audit",
    finalPath: "/compliance/dashboard/",
    build: true,
  },
];
const VIEWPORTS = [
  { width: 1440, height: 1000 },
  { width: 1024, height: 900 },
  { width: 768, height: 900 },
  { width: 390, height: 844 },
];
const THEMES = ["light", "dark"];

function command(args, extraEnv = {}) {
  const result = spawnSync(PYTHON, args, {
    cwd: ROOT,
    env: { ...process.env, ...extraEnv },
    encoding: "utf8",
    shell: false,
  });
  if (result.status !== 0) {
    throw new Error(`${PYTHON} ${args.join(" ")} failed\n${result.stderr || result.stdout}`);
  }
  return `${result.stdout || ""}\n${result.stderr || ""}`;
}

function createSession() {
  if ((process.env.RMC_TENANT_SESSIONID || "").trim()) {
    return (process.env.RMC_TENANT_SESSIONID || "").trim();
  }
  const code = [
    "from datetime import timedelta",
    "from django.conf import settings",
    "from django.test import Client",
    "from django.utils import timezone",
    "from apps.schools.models import School",
    `s=School.objects.get(slug=${JSON.stringify(HOST.split(".")[0])})`,
    "u=s.memberships.select_related('user').filter(user__username='demo.admin', suspended_at__isnull=True).first().user",
    `c=Client(HTTP_HOST=${JSON.stringify(HOST)})`,
    "c.force_login(u)",
    "session=c.session",
    "session['mfa_verified']=True",
    "session['mfa_verified_until']=(timezone.now()+timedelta(days=30)).isoformat()",
    "session.save()",
    "print('RMC_BROWSER_SESSION='+c.cookies[settings.SESSION_COOKIE_NAME].value)",
  ].join("; ");
  const output = command(["manage.py", "shell", "-c", code]);
  const match = output.match(/RMC_BROWSER_SESSION=([^\s]+)/);
  if (!match) throw new Error("Could not create the local authenticated tenant browser session");
  return match[1];
}

function probe() {
  return new Promise((resolve) => {
    const request = http.get(
      {
        hostname: "127.0.0.1",
        port: PORT,
        path: "/authentication/login/",
        headers: { Host: HOST },
        timeout: 5000,
      },
      (response) => {
        response.resume();
        resolve(response.statusCode || 0);
      },
    );
    request.on("error", () => resolve(0));
    request.on("timeout", () => {
      request.destroy();
      resolve(0);
    });
  });
}

async function waitForServer() {
  for (let attempt = 0; attempt < 90; attempt += 1) {
    if ((await probe()) > 0) return;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`Django did not become ready on ${HOST}:${PORT}`);
}

async function inspectPage(page, route, viewport, theme, resourceFailures) {
  return page.evaluate(
    ({ route, viewport, theme, buildId, resourceFailures }) => {
      const isVisible = (element) => {
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
      const h1s = [...document.querySelectorAll("h1")].filter(isVisible);
      const stylesheets = [...document.querySelectorAll('link[rel="stylesheet"]')];
      const stylesheetUrls = stylesheets.map((link) => link.href);
      const duplicateCss = [
        ...new Set(
          stylesheetUrls.filter((href, index) => stylesheetUrls.indexOf(href) !== index),
        ),
      ];
      const root = document.querySelector(`[data-rmc-tenant-ops-build="${buildId}"]`);
      const rootRect = root?.getBoundingClientRect() || null;
      const parentRect = root?.parentElement?.getBoundingClientRect() || null;
      const parentStyle = root?.parentElement ? getComputedStyle(root.parentElement) : null;
      const parentContentWidth = parentRect && parentStyle
        ? parentRect.width - Number.parseFloat(parentStyle.paddingLeft || "0") - Number.parseFloat(parentStyle.paddingRight || "0")
        : null;
      const fullWidthRatio =
        rootRect && parentContentWidth ? rootRect.width / parentContentWidth : null;
      const grids = [
        ...document.querySelectorAll(
          ".rmc-ops-card-grid, .rmc-config-grid, .proof-catalog-grid, .rmc-ops-kpis",
        ),
      ].filter(isVisible);
      const gridTracks = grids.map((grid) => ({
        selector: grid.className,
        columns: (getComputedStyle(grid).gridTemplateColumns.match(/-?\d+(?:\.\d+)?px/g) || [])
          .map(Number.parseFloat)
          .filter((value) => value > 0),
      }));
      const rawIcons = [...document.querySelectorAll(".material-symbols-outlined")]
        .filter(isVisible)
        .filter((element) => !getComputedStyle(element).fontFamily.toLowerCase().includes("material symbols"))
        .map((element) => (element.textContent || "").trim())
        .filter(Boolean);
      const main =
        document.querySelector("[data-rmc-tenant-ops-build]") ||
        document.querySelector("main") ||
        document.querySelector("#content-main");
      const simulatedActions = main
        ? [...main.querySelectorAll('a[href="#"], a[href^="javascript:"]')]
            .filter(isVisible)
            .map((anchor) => (anchor.textContent || "").trim())
        : [];
      const unsafePostForms = main
        ? [...main.querySelectorAll('form[method="post" i]')]
            .filter(isVisible)
            .filter((form) => !form.querySelector('input[name="csrfmiddlewaretoken"]')).length
        : 0;
      const centerX = innerWidth / 2;
      const centerY = innerHeight / 2;
      const unexpectedFixedOverlays = [...document.querySelectorAll("body *")]
        .filter(isVisible)
        .filter((element) => getComputedStyle(element).position === "fixed")
        .filter((element) => {
          const rect = element.getBoundingClientRect();
          const coversCenter =
            rect.left < centerX && rect.right > centerX && rect.top < centerY && rect.bottom > centerY;
          const isDialog = element.matches('[role="dialog"], dialog, .modal, [aria-modal="true"]');
          return coversCenter && !isDialog;
        })
        .map((element) => element.id || String(element.className || element.tagName).slice(0, 160));
      return {
        route: route.key,
        requestedPath: route.path,
        finalUrl: location.href,
        finalPath: location.pathname,
        hostname: location.hostname,
        statusTheme: theme,
        viewport,
        h1Count: h1s.length,
        h1Text: h1s.map((element) => (element.textContent || "").trim()),
        horizontalOverflow: Math.max(
          0,
          document.documentElement.scrollWidth - document.documentElement.clientWidth,
        ),
        duplicateCss,
        stylesheetLinksInBody: document.body.querySelectorAll('link[rel="stylesheet"]').length,
        resourceFailures,
        hasApprovedBuild: Boolean(root),
        fullWidthRatio,
        gridTracks,
        rawIcons,
        simulatedActions,
        unsafePostForms,
        unexpectedFixedOverlays,
        actionCount: main ? main.querySelectorAll("a[href], button, form").length : 0,
        computedColorScheme: getComputedStyle(document.documentElement).colorScheme,
        computedBackground: getComputedStyle(document.body).backgroundColor,
      };
    },
    { route, viewport, theme, buildId: BUILD_ID, resourceFailures },
  );
}

function findingsFor(result, route) {
  const findings = [];
  const expectedFinal = route.finalPath || route.path.split("?")[0];
  if (result.hostname !== HOST) findings.push(`wrong hostname ${result.hostname}`);
  if (result.finalPath !== expectedFinal) findings.push(`wrong final path ${result.finalPath}`);
  if (result.h1Count !== 1) findings.push(`visible H1 count ${result.h1Count}`);
  if (result.horizontalOverflow > 1) {
    findings.push(`horizontal overflow ${result.horizontalOverflow}px`);
  }
  if (result.duplicateCss.length) findings.push(`duplicate CSS ${result.duplicateCss.length}`);
  if (result.stylesheetLinksInBody) {
    findings.push(`stylesheet links in body ${result.stylesheetLinksInBody}`);
  }
  if (result.resourceFailures.length) {
    findings.push(`broken resources ${result.resourceFailures.length}`);
  }
  if (route.build && !result.hasApprovedBuild) findings.push("approved build marker missing");
  if (route.build && result.fullWidthRatio !== null && result.fullWidthRatio < 0.9) {
    findings.push(`canvas width ratio ${result.fullWidthRatio.toFixed(3)}`);
  }
  if (result.viewport.width <= 1024) {
    const multiColumn = result.gridTracks.filter((grid) => grid.columns.length > 1);
    if (multiColumn.length) findings.push(`responsive grids still multi-column ${multiColumn.length}`);
  }
  if (result.rawIcons.length) findings.push(`raw icon names ${result.rawIcons.join(", ")}`);
  if (result.simulatedActions.length) {
    findings.push(`simulated actions ${result.simulatedActions.join(", ")}`);
  }
  if (result.unsafePostForms) findings.push(`POST forms without CSRF ${result.unsafePostForms}`);
  if (result.unexpectedFixedOverlays.length) {
    findings.push(`unexpected fixed overlays ${result.unexpectedFixedOverlays.join(", ")}`);
  }
  if (!result.actionCount) findings.push("no genuine page actions");
  return findings;
}

async function main() {
  fs.mkdirSync(OUTPUT, { recursive: true });
  const sessionId = createSession();
  const log = fs.openSync(SERVER_LOG, "a");
  const server = spawn(PYTHON, ["manage.py", "runserver", `127.0.0.1:${PORT}`, "--noreload"], {
    cwd: ROOT,
    env: {
      ...process.env,
      DEBUG: "1",
      SECURE_SSL_REDIRECT: "0",
      SESSION_COOKIE_SECURE: "0",
      CSRF_COOKIE_SECURE: "0",
      RMC_FORCE_DB_SESSIONS: "1",
      PYTHONUNBUFFERED: "1",
    },
    stdio: ["ignore", log, log],
    windowsHide: true,
  });
  let browser;
  try {
    await waitForServer();
    browser = await chromium.launch({
      headless: true,
      args: [`--host-resolver-rules=MAP ${HOST} 127.0.0.1`],
    });
    const results = [];
    for (const theme of THEMES) {
      for (const viewport of VIEWPORTS) {
        const context = await browser.newContext({
          viewport,
          colorScheme: theme,
          serviceWorkers: "block",
        });
        await context.addCookies([
          {
            name: process.env.RMC_SESSION_COOKIE_NAME || "sessionid",
            value: sessionId,
            domain: HOST,
            path: "/",
            httpOnly: true,
            sameSite: "Lax",
          },
        ]);
        await context.addInitScript(({ theme }) => {
          localStorage.setItem("theme", theme);
          localStorage.setItem("rmc-theme", theme);
          document.documentElement.dataset.theme = theme;
        }, { theme });
        for (const route of ROUTES) {
          const page = await context.newPage();
          const resourceFailures = [];
          page.on("response", (response) => {
            const request = response.request();
            if (response.status() >= 400 && new URL(response.url()).hostname === HOST) {
              resourceFailures.push({
                status: response.status(),
                type: request.resourceType(),
                url: response.url(),
              });
            }
          });
          page.on("requestfailed", (request) => {
            resourceFailures.push({
              status: 0,
              type: request.resourceType(),
              url: request.url(),
              error: request.failure()?.errorText || "request failed",
            });
          });
          const response = await page.goto(`http://${HOST}:${PORT}${route.path}`, {
            waitUntil: "domcontentloaded",
            timeout: 120000,
          });
          await page.waitForTimeout(350);
          const result = await inspectPage(page, route, viewport, theme, resourceFailures);
          result.httpStatus = response?.status() || 0;
          result.findings = findingsFor(result, route);
          if (result.httpStatus !== 200) result.findings.push(`HTTP ${result.httpStatus}`);
          const shouldCapture =
            (viewport.width === 1440 && theme === "dark") ||
            (viewport.width === 390 && theme === "light") ||
            result.findings.length > 0;
          if (shouldCapture) {
            const shot = `${route.key}-${viewport.width}-${theme}.png`;
            await page.screenshot({ path: path.join(OUTPUT, shot), fullPage: true });
            result.screenshot = shot;
          }
          results.push(result);
          await page.close();
        }
        await context.close();
      }
    }
    const findingCount = results.reduce((total, result) => total + result.findings.length, 0);
    const payload = {
      generatedAt: new Date().toISOString(),
      host: HOST,
      buildId: BUILD_ID,
      routes: ROUTES.map((route) => route.path),
      viewportWidths: VIEWPORTS.map((viewport) => viewport.width),
      themes: THEMES,
      resultCount: results.length,
      findingCount,
      results,
    };
    fs.writeFileSync(REPORT, `${JSON.stringify(payload, null, 2)}\n`);
    if (findingCount) {
      console.error(`TENANT_CONFIGURATION_OPERATIONS_BROWSER_FAIL findings=${findingCount}`);
      for (const result of results.filter((item) => item.findings.length)) {
        console.error(`  ${result.route} ${result.viewport.width} ${result.statusTheme}: ${result.findings.join("; ")}`);
      }
      process.exitCode = 1;
      return;
    }
    console.log(
      `TENANT_CONFIGURATION_OPERATIONS_BROWSER_PASS results=${results.length} host=${HOST}`,
    );
  } finally {
    if (browser) await browser.close().catch(() => undefined);
    server.kill();
    fs.closeSync(log);
  }
}

await main();
