#!/usr/bin/env node
/**
 * Run tenant abrupt-end sweep in sequential 25-route slices (Windows-safe).
 * Usage: node scripts/run_tenant_abrupt_end_batches.mjs
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function resolvePython() {
  if (process.env.VISUAL_QA_PYTHON) {
    return process.env.VISUAL_QA_PYTHON;
  }
  const candidates = [
    path.join(repo, '.venv', 'Scripts', 'python.exe'),
    path.join(repo, '.venv', 'bin', 'python'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

const py = resolvePython();
const orchestrator = path.join(repo, 'scripts', 'run_tenant_abrupt_end_e2e.mjs');
const batchSize = parseInt(process.env.TENANT_SWEEP_BATCH_SIZE || '25', 10);
const ledgerPath = path.join(repo, 'docs/generated/portal_tenant_sweep_routes.json');
const partialPath = path.join(repo, 'var/tenant-abrupt-end-sweep.partial.json');
const finalPath = path.join(repo, 'var/tenant-abrupt-end-sweep.json');
const stableDb = path.join(repo, 'db_playwright_tenant_abrupt.sqlite3');

spawnSync(py, [path.join(repo, 'scripts/generate_portal_tenant_sweep_routes.py'), '--write'], {
  cwd: repo,
  env: { ...process.env, TENANT_SWEEP_MAX: '200' },
  stdio: 'inherit',
  shell: false,
});

const routeCount = (() => {
  const data = JSON.parse(fs.readFileSync(ledgerPath, 'utf8'));
  const routes = Array.isArray(data.routes) ? data.routes : [];
  const maxRoutes = parseInt(process.env.TENANT_SWEEP_MAX || '200', 10);
  return (maxRoutes > 0 ? routes.slice(0, maxRoutes) : routes).filter(
    (row) => row.sweep !== false,
  ).length;
})();

const batchTotal = Math.ceil(routeCount / batchSize);
console.log(
  `=== tenant abrupt-end batches: ${routeCount} routes, ${batchTotal} slices (size=${batchSize}) ===`,
);

if (fs.existsSync(partialPath)) {
  fs.unlinkSync(partialPath);
}
if (fs.existsSync(finalPath)) {
  fs.unlinkSync(finalPath);
}

function mergePartialResults() {
  if (!fs.existsSync(partialPath)) {
    return [];
  }
  const partial = JSON.parse(fs.readFileSync(partialPath, 'utf8'));
  return Array.isArray(partial.results) ? partial.results : [];
}

function savePartialResults(results, totalPlanned) {
  fs.mkdirSync(path.dirname(partialPath), { recursive: true });
  fs.writeFileSync(
    partialPath,
    `${JSON.stringify({ results, totalPlanned }, null, 2)}\n`,
  );
}

function mergeBatchSummary(allResults, totalPlanned) {
  const tenantResults = allResults.filter((r) => r.surface === 'tenant');
  const layoutFailed = tenantResults.filter(
    (r) =>
      r.ok === false &&
      !(r.failures || []).every(
        (f) => f === 'exception' && /ERR_CONNECTION|Timeout/i.test(String(r.error || '')),
      ),
  );
  const layoutProven = tenantResults.filter(
    (r) =>
      r.ok === true &&
      !r.skipped &&
      !/\/authentication\/(login|mfa\/verify)/i.test(String(r.path || '')),
  ).length;
  const infraSkipped = tenantResults.filter((r) => r.skipped).length;
  const failed = layoutFailed.filter((r) =>
    (r.failures || []).some((f) => f !== 'exception'),
  ).length;
  return {
    generatedAt: new Date().toISOString(),
    sweepTier: 'tenant',
    managerPlanned: 0,
    tenantPlanned: totalPlanned,
    managerTested: 0,
    tenantTested: tenantResults.length,
    layoutProven,
    resultsCount: tenantResults.length,
    passed: tenantResults.filter((r) => r.ok).length,
    failed,
    skipped: tenantResults.filter((r) => r.skipped).length,
    infraSkipped,
    failedUrls: layoutFailed.map((r) => ({
      url: r.url,
      failures: r.failures,
      error: r.error,
    })),
    results: tenantResults,
  };
}

let status = 0;
let allResults = [];

for (let batchIndex = 0; batchIndex < batchTotal; batchIndex += 1) {
  const offset = batchIndex * batchSize;
  console.log(
    `=== tenant abrupt-end batches: slice ${batchIndex + 1}/${batchTotal} (offset=${offset}) ===`,
  );
  const env = {
    ...process.env,
    TENANT_SWEEP_ROUTE_OFFSET: String(offset),
    TENANT_SWEEP_MAX: String(batchSize),
    TENANT_SWEEP_BATCH_ONLY: '',
    DB_FILE: stableDb,
    USE_FILE_LOGGING: 'False',
    TENANT_SWEEP_SKIP_BOOT: batchIndex > 0 ? '1' : '0',
  };
  const result = spawnSync(process.execPath, [orchestrator], {
    cwd: repo,
    env,
    stdio: 'inherit',
    shell: false,
  });
  const auditPath = path.join(repo, 'docs/generated/admin_playwright_sweep_audit.json');
  if (!fs.existsSync(auditPath)) {
    console.error(`missing audit after slice ${batchIndex + 1}`);
    status = result.status ?? 1;
    break;
  }
  const audit = JSON.parse(fs.readFileSync(auditPath, 'utf8'));
  const batchResults = (audit.results || []).filter((row) => row.surface === 'tenant');
  const batchUrls = new Set(
    JSON.parse(fs.readFileSync(ledgerPath, 'utf8'))
      .routes.slice(offset, offset + batchSize)
      .map((row) => row.inner || row.path),
  );
  allResults = allResults.filter((row) => !batchUrls.has(row.url || row.inner));
  allResults.push(...batchResults);
  savePartialResults(allResults, routeCount);

  if (result.status !== 0) {
    console.error(`slice ${batchIndex + 1} failed with exit ${result.status ?? 1}`);
    status = result.status ?? 1;
    break;
  }
}

if (status === 0 && allResults.length >= routeCount) {
  const merged = mergeBatchSummary(allResults, routeCount);
  fs.writeFileSync(finalPath, `${JSON.stringify(merged, null, 2)}\n`);
  console.log(`Wrote ${finalPath}`);
  console.log(JSON.stringify({ ...merged, results: undefined }, null, 2));
  if (
    merged.tenantTested >= routeCount &&
    merged.layoutProven >= routeCount &&
    merged.failed === 0 &&
    merged.infraSkipped === 0
  ) {
    console.log('TENANT_ABRUPT_END_SWEEP_PASS');
    spawnSync(py, [path.join(repo, 'scripts/generate_tenant_surface_coverage_matrix.py'), '--write'], {
      cwd: repo,
      stdio: 'inherit',
      shell: false,
    });
    console.log('TENANT_ABRUPT_END_SWEEP_E2E_PASS');
  } else {
    status = 1;
  }
}

if (status === 0) {
  console.log('TENANT_ABRUPT_END_BATCHES_PASS');
}
process.exit(status);
