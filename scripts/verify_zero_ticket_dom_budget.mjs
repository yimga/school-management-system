#!/usr/bin/env node
/**
 * Forensic master prompt §4 Vector 3 — DOM/CLS/abrupt-end gate for self-healing surfaces.
 * Delegates CLS + scroll FPS to verify_playwright_performance_budgets.mjs and adds
 * zero-ticket workflow hub to the target set.
 *
 * Usage:
 *   node scripts/verify_zero_ticket_dom_budget.mjs
 *   PERF_PLAYWRIGHT_STRICT=1 node scripts/verify_zero_ticket_dom_budget.mjs
 */
import { spawnSync } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const PERF_SCRIPT = path.join(__dirname, 'verify_playwright_performance_budgets.mjs');

const extraTargets = [
  { label: 'Campus workflow canvas hub', path: '/siteconfig/zero-ticket/workflows/' },
];

process.env.PERF_PLAYWRIGHT_EXTRA_TARGETS = JSON.stringify(extraTargets);

const result = spawnSync(process.execPath, [PERF_SCRIPT], {
  cwd: ROOT,
  stdio: 'inherit',
  env: { ...process.env },
});

if (result.status !== 0) {
  console.error('verify_zero_ticket_dom_budget: FAIL (Playwright perf budgets)');
  process.exit(result.status ?? 1);
}
console.log('verify_zero_ticket_dom_budget: PASS');
process.exit(0);
