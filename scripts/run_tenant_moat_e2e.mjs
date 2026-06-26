#!/usr/bin/env node
/**
 * Boot Django + seed demo-school/report-card, then run tenant moat Playwright suite.
 * Windows-safe alternative to Playwright webServer (migrate+seed can exceed 2 min).
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const port = (process.env.VISUAL_QA_TENANT_PHASE_PORT || process.env.VISUAL_QA_PORT || '8016').trim();
const slug = (process.env.TENANT_SLUG || 'demo-school').trim();
const password = process.env.E2E_TENANT_PASSWORD || 'Test1234';
const loginUrl = `http://127.0.0.1:${port}/t/${slug}/authentication/login/`;

function resolvePython() {
  if (process.env.VISUAL_QA_PYTHON) {
    return process.env.VISUAL_QA_PYTHON;
  }
  for (const candidate of [
    path.join(repo, '.venv', 'Scripts', 'python.exe'),
    path.join(repo, '.venv', 'bin', 'python'),
  ]) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

function runSync(args, extraEnv = {}) {
  const py = resolvePython();
  const result = spawnSync(py, args, {
    cwd: repo,
    env: { ...process.env, ...extraEnv },
    stdio: 'inherit',
    shell: false,
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function probe(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      res.resume();
      resolve(res.statusCode ?? 0);
    });
    req.on('error', () => resolve(0));
    req.setTimeout(4000, () => {
      req.destroy();
      resolve(0);
    });
  });
}

async function waitForServer(maxSeconds = 240) {
  for (let i = 0; i < maxSeconds; i += 1) {
    const code = await probe(loginUrl);
    if (code >= 200 && code < 500) {
      return;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  console.error(`run_tenant_moat_e2e: server not ready at ${loginUrl}`);
  process.exit(1);
}

const py = resolvePython();
const baseEnv = {
  REDIS_URL: '',
  RMC_FORCE_DB_SESSIONS: '1',
  SECURE_SSL_REDIRECT: '0',
  DEBUG: '1',
  LOGIN_POW_ENABLED: '0',
  RMC_E2E_BYPASS_MFA: '1',
  CSRF_COOKIE_SECURE: '0',
  SESSION_COOKIE_SECURE: '0',
  VISUAL_QA_PORT: port,
  VISUAL_QA_TENANT_PHASE_PORT: port,
  TENANT_SLUG: slug,
  E2E_TENANT_PASSWORD: password,
  RMC_E2E_SEED_REPORT_CARD: '1',
};

console.log('=== tenant moat e2e: migrate ===');
runSync(['manage.py', 'migrate', '--noinput'], baseEnv);

console.log('=== tenant moat e2e: ensure demo-school ===');
runSync(['manage.py', 'ensure_developer_sandbox_tenant', `--school-slug=${slug}`], baseEnv);

console.log('=== tenant moat e2e: seed demo users ===');
runSync(
  [
    'manage.py',
    'seed_demo_tenant_users',
    `--school-slug=${slug}`,
    `--password=${password}`,
  ],
  baseEnv,
);

console.log('=== tenant moat e2e: seed report-card fixture ===');
runSync(
  [
    'manage.py',
    'seed_report_card_e2e',
    `--school-slug=${slug}`,
    `--password=${password}`,
  ],
  baseEnv,
);

console.log(`=== tenant moat e2e: runserver 127.0.0.1:${port} ===`);
const server = spawn(
  py,
  ['manage.py', 'runserver', `127.0.0.1:${port}`, '--noreload'],
  {
    cwd: repo,
    env: { ...process.env, ...baseEnv, PYTHONUNBUFFERED: '1' },
    stdio: 'inherit',
    shell: false,
  },
);

const killServer = () => {
  if (server.pid) {
    try {
      process.kill(server.pid);
    } catch (_e) {
      /* ignore */
    }
  }
};
process.on('exit', killServer);

await waitForServer();

console.log('=== tenant moat e2e: Playwright ===');
const pwCli = path.join(repo, 'node_modules', '@playwright', 'test', 'cli.js');
const pw = spawnSync(
  process.execPath,
  [
    pwCli,
    'test',
    'tests/e2e/offline-multiday-indexeddb.spec.js',
    'tests/e2e/offline-authenticated-sync.spec.js',
    'tests/e2e/report-card-hash-parent.spec.js',
    'tests/e2e/tenant-shell-a11y.spec.js',
    '--project=offline-indexeddb-chromium',
    '--project=offline-sync-chromium',
  ],
  {
    cwd: repo,
    env: {
      ...process.env,
      ...baseEnv,
      CI: '1',
      RMC_E2E_EXTERNAL_SERVER: '1',
      PLAYWRIGHT_TENANT_BASE_URL: `http://127.0.0.1:${port}/t/${slug}`,
    },
    stdio: 'inherit',
    shell: false,
  },
);

killServer();

if (pw.status === 0) {
  console.log('TENANT_MOAT_E2E_PASS');
}
process.exit(pw.status ?? 1);
