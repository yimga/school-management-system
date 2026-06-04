#!/usr/bin/env node
/**
 * Export manager Playwright storage (when E2E creds set), then run workflow-progress E2E.
 */
const { execFileSync, spawnSync } = require('child_process');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const python =
  process.env.VISUAL_QA_PYTHON ||
  (process.platform === 'win32' ? 'python' : 'python3');

const skipExport = ['1', 'true', 'yes'].includes(
  String(process.env.E2E_SKIP_MANAGER_EXPORT || '').toLowerCase()
);

if (process.env.E2E_LOGIN_USER && !skipExport) {
  const exportEnv = {
    ...process.env,
    REDIS_URL: '',
    RMC_FORCE_DB_SESSIONS: '1',
    VISUAL_QA_USERNAME: process.env.E2E_LOGIN_USER,
    VISUAL_QA_PASSWORD:
      process.env.E2E_LOGIN_PASSWORD ||
      process.env.VISUAL_QA_PASSWORD ||
      'Sch00l_1234',
  };
  const dbFile = (process.env.DB_FILE || '').trim();
  if (!dbFile) {
    try {
      const fs = require('fs');
      const envLocal = path.join(ROOT, '.env.local');
      if (fs.existsSync(envLocal)) {
        const match = fs.readFileSync(envLocal, 'utf8').match(/^DB_FILE=(.+)$/m);
        if (match && match[1].trim()) {
          exportEnv.DB_FILE = match[1].trim();
        }
      }
    } catch (_e) {
      /* optional */
    }
  }
  execFileSync(python, ['scripts/export_manager_playwright_storage.py'], {
    cwd: ROOT,
    stdio: 'inherit',
    env: exportEnv,
  });
}

const playwright = spawnSync(
  'npx',
  ['playwright', 'test', 'tests/e2e/workflow-progress.spec.js', ...process.argv.slice(2)],
  { cwd: ROOT, stdio: 'inherit', shell: true }
);
process.exit(playwright.status === null ? 1 : playwright.status);
