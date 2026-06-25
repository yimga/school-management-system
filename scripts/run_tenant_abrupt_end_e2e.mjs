#!/usr/bin/env node
/**
 * Batch 1729 — boot Django, seed demo-school admin MFA, run 200-route tenant abrupt-end sweep.
 * Cross-platform entry: npm run sweep:abrupt-end:tenant:e2e
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_TOTP_HEX = 'eab95095c004f245721ba0fa7ebf82d5dc73';
const port = (process.env.VISUAL_QA_PORT || '8015').trim();
const slug = (process.env.TENANT_SLUG || 'demo-school').trim();
const tenantHost = process.env.VISUAL_QA_TENANT_HOST || `${slug}.runmycampus.com`;
const loginUrl = `http://127.0.0.1:${port}/t/${slug}/authentication/login/`;
const defaultGate = path.join(repo, 'var', 'e2e', 'role_home_gate_v2.sqlite3');
const legacyGate = path.join(repo, 'var', 'e2e', 'role_home_gate.sqlite3');
const gateSnapshot = (
  process.env.RMC_E2E_GATE_SNAPSHOT ||
  (fs.existsSync(defaultGate) ? defaultGate : '') ||
  (fs.existsSync(legacyGate) ? legacyGate : '')
).trim();
const dbFile =
  process.env.DB_FILE ||
  path.join(repo, `db_playwright_tenant_abrupt_${process.pid}.sqlite3`);

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

function runSync(args, extraEnv = {}, stdio = 'inherit') {
  const py = resolvePython();
  const result = spawnSync(py, args, {
    cwd: repo,
    env: { ...process.env, ...extraEnv },
    stdio,
    shell: false,
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
  return result;
}

function migrateDatabase(extraEnv) {
  const check = spawnSync(resolvePython(), ['manage.py', 'migrate', '--check'], {
    cwd: repo,
    env: { ...process.env, ...extraEnv },
    stdio: 'pipe',
    shell: false,
  });
  if (check.status === 0) {
    console.log('=== tenant abrupt-end e2e: migrate skipped (schema current) ===');
    return;
  }
  runSync(['manage.py', 'migrate', '--noinput'], extraEnv);
}

function probe(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      res.resume();
      resolve(res.statusCode ?? 0);
    });
    req.on('error', () => resolve(0));
    req.setTimeout(8000, () => {
      req.destroy();
      resolve(0);
    });
  });
}

async function waitForServer(maxSeconds = 360) {
  let stableOk = 0;
  for (let i = 0; i < maxSeconds; i += 1) {
    const code = await probe(loginUrl);
    if (code >= 200 && code < 500) {
      stableOk += 1;
      if (stableOk >= 3) {
        return;
      }
    } else {
      stableOk = 0;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  console.error(`run_tenant_abrupt_end_e2e: server not ready at ${loginUrl}`);
  process.exit(1);
}

const py = resolvePython();
const baseEnv = {
  DB_FILE: dbFile,
  VISUAL_QA_PYTHON: py,
  DJANGO_SQLITE_TIMEOUT: process.env.DJANGO_SQLITE_TIMEOUT || '90',
  REDIS_URL: '',
  RMC_FORCE_DB_SESSIONS: '1',
  SECURE_SSL_REDIRECT: '0',
  DEBUG: process.env.DEBUG ?? '0',
  CSRF_COOKIE_SECURE: '0',
  SESSION_COOKIE_SECURE: '0',
  RMC_DEPLOYMENT_PROFILE: 'online',
  OBSERVABILITY_METRICS_BACKEND: 'noop',
  ALLOWED_HOSTS:
    process.env.ALLOWED_HOSTS ||
    '127.0.0.1,localhost,testserver,runmycampus.com,.runmycampus.com',
  MULTI_TENANT_BASE_DOMAIN: process.env.MULTI_TENANT_BASE_DOMAIN || 'runmycampus.com',
  VISUAL_QA_PORT: port,
  VISUAL_QA_TENANT_HOST: tenantHost,
  TENANT_SLUG: slug,
  TENANT_SWEEP_SLUG: slug,
  TENANT_SWEEP_MAX: process.env.TENANT_SWEEP_MAX || '200',
  TENANT_SWEEP_USERNAME: process.env.TENANT_SWEEP_USERNAME || 'demo.admin',
  TENANT_SWEEP_PASSWORD: process.env.TENANT_SWEEP_PASSWORD || 'Test1234',
  VISUAL_QA_TOTP_HEX_KEY:
    process.env.VISUAL_QA_TOTP_HEX_KEY ||
    process.env.VISUAL_QA_TOTP_HEX ||
    DEFAULT_TOTP_HEX,
  DB_LOG_LEVEL: process.env.DB_LOG_LEVEL || 'WARNING',
  LOGIN_POW_ENABLED: '0',
  PYTHONUTF8: '1',
};
const seedEnv = { ...baseEnv, DEBUG: '1' };

function removeSqliteDbFiles(dbPath) {
  for (const suffix of ['', '-wal', '-shm']) {
    const candidate = suffix ? `${dbPath}${suffix}` : dbPath;
    if (!fs.existsSync(candidate)) {
      continue;
    }
    try {
      fs.unlinkSync(candidate);
    } catch (err) {
      console.warn(`could not remove ${candidate}: ${err}`);
    }
  }
}

console.log('=== tenant abrupt-end e2e: route ledger ===');
runSync(['scripts/generate_portal_tenant_sweep_routes.py', '--write'], seedEnv);

console.log('=== tenant abrupt-end e2e: migrate ===');
if (gateSnapshot && fs.existsSync(gateSnapshot)) {
  fs.copyFileSync(gateSnapshot, dbFile);
  console.log(`seeded e2e db from gate snapshot ${gateSnapshot}`);
} else if (process.env.RMC_E2E_KEEP_DB !== '1' && fs.existsSync(dbFile)) {
  removeSqliteDbFiles(dbFile);
  console.log(`removed stale e2e db ${dbFile}`);
}
migrateDatabase(seedEnv);

console.log(`=== tenant abrupt-end e2e: ensure developer sandbox (${slug}) ===`);
runSync(
  [
    'manage.py',
    'ensure_developer_sandbox_tenant',
    `--school-slug=${slug}`,
    `--password=${baseEnv.TENANT_SWEEP_PASSWORD}`,
  ],
  seedEnv,
);

console.log('=== tenant abrupt-end e2e: seed TOTP for demo.admin ===');
runSync(
  [
    '-c',
    `
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
from django_otp.plugins.otp_totp.models import TOTPDevice
key = os.environ.get('VISUAL_QA_TOTP_HEX_KEY', '${DEFAULT_TOTP_HEX}')
username = 'demo.admin'
user = get_user_model().objects.filter(username=username).first()
if not user:
    raise SystemExit(f'demo tenant user missing: {username}')
user.is_active = True
user.is_staff = True
from apps.accounts.models import Permission
perm, _ = Permission.objects.get_or_create(
    code="settings.manage",
    defaults={"name": "Manage settings"},
)
user.feature_permissions.add(perm)
user.save()
TOTPDevice.objects.filter(user=user).delete()
device = TOTPDevice.objects.create(user=user, name='e2e-playwright', confirmed=True)
device.key = key
device.save()
print(f'Seeded TOTP e2e-playwright for {username}')
`.trim(),
  ],
  seedEnv,
);

const artifactDir = path.join(repo, 'artifacts', 'tenant-abrupt-end-e2e');
fs.mkdirSync(artifactDir, { recursive: true });
const serverLog = path.join(artifactDir, 'runserver.log');
fs.writeFileSync(serverLog, '');
const serverLogFd = fs.openSync(serverLog, 'a');

console.log(`=== tenant abrupt-end e2e: runserver 127.0.0.1:${port} ===`);
const server = spawn(
  py,
  ['manage.py', 'runserver', `127.0.0.1:${port}`, '--noreload'],
  {
    cwd: repo,
    env: { ...process.env, ...baseEnv, PYTHONUNBUFFERED: '1' },
    stdio: ['ignore', serverLogFd, serverLogFd],
    shell: false,
  },
);

let serverExited = false;
server.on('exit', (code) => {
  serverExited = true;
  if (code && code !== 0) {
    console.error(`run_tenant_abrupt_end_e2e: runserver exited ${code}`);
  }
});

const stopServer = () => {
  if (!serverExited && server.pid) {
    try {
      if (process.platform === 'win32') {
        spawnSync('taskkill', ['/pid', String(server.pid), '/t', '/f'], {
          stdio: 'ignore',
          shell: false,
        });
      } else {
        process.kill(server.pid);
      }
    } catch (_e) {
      /* ignore */
    }
  }
};

process.on('exit', () => {
  stopServer();
});
for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    stopServer();
    process.exit(130);
  });
}

await waitForServer(parseInt(process.env.SWEEP_HEALTH_SECS || '360', 10));
await new Promise((r) => setTimeout(r, 3000));

console.log('=== tenant abrupt-end e2e: Playwright sweep (200 routes) ===');
const sweepEnv = {
  ...process.env,
  ...baseEnv,
  SWEEP_TIER: 'tenant',
  SWEEP_INCLUDE_TENANT: '1',
  USE_TENANT_SUBDOMAIN: '1',
  TENANT_E2E_SUBDOMAIN: '1',
  TENANT_BASE_URL: `http://${tenantHost}:${port}`,
  PLAYWRIGHT_TENANT_HOST_RULES: `MAP ${tenantHost} 127.0.0.1`,
  TENANT_SWEEP_MAX_INFRA_SKIP: process.env.TENANT_SWEEP_MAX_INFRA_SKIP || '0',
};
const sweep = spawnSync(
  process.execPath,
  [path.join(repo, 'scripts', 'verify_platform_abrupt_end_sweep.mjs')],
  {
    cwd: repo,
    env: sweepEnv,
    stdio: 'inherit',
    shell: false,
  },
);

stopServer();

if (sweep.status !== 0) {
  process.exit(sweep.status ?? 1);
}

console.log('=== tenant abrupt-end e2e: regenerate coverage matrix ===');
runSync(['scripts/generate_tenant_surface_coverage_matrix.py', '--write'], seedEnv);

console.log('TENANT_ABRUPT_END_SWEEP_E2E_PASS');
process.exit(0);
