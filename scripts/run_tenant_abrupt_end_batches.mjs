#!/usr/bin/env node
/**
 * Run tenant abrupt-end sweep in sequential batches (Windows-safe resume).
 * Usage: node scripts/run_tenant_abrupt_end_batches.mjs
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const orchestrator = path.join(repo, 'scripts', 'run_tenant_abrupt_end_e2e.mjs');
const batchSize = parseInt(process.env.TENANT_SWEEP_BATCH_SIZE || '25', 10);
const ledgerPath = path.join(repo, 'docs/generated/portal_tenant_sweep_routes.json');
const partialPath = path.join(repo, 'var/tenant-abrupt-end-sweep.partial.json');
const stableDb = path.join(repo, 'db_playwright_tenant_abrupt.sqlite3');

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
  `=== tenant abrupt-end batches: ${routeCount} routes, ${batchTotal} batches (size=${batchSize}) ===`,
);

if (fs.existsSync(partialPath)) {
  fs.unlinkSync(partialPath);
}

let status = 0;
for (let batchIndex = 0; batchIndex < batchTotal; batchIndex += 1) {
  console.log(`=== tenant abrupt-end batches: starting batch ${batchIndex + 1}/${batchTotal} ===`);
  const env = {
    ...process.env,
    TENANT_SWEEP_BATCH_ONLY: String(batchIndex),
    TENANT_SWEEP_BATCH_TOTAL: String(batchTotal),
    TENANT_SWEEP_ROUTE_TOTAL: String(routeCount),
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
  if (result.status !== 0) {
    console.error(`batch ${batchIndex + 1} failed with exit ${result.status ?? 1}`);
    status = result.status ?? 1;
    break;
  }
}

if (status === 0) {
  console.log('TENANT_ABRUPT_END_BATCHES_PASS');
}
process.exit(status);
