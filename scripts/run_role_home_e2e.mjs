#!/usr/bin/env node
/**
 * Batch 1711 — boot Django, seed demo-school personas, run role-home visual sweep.
 * Cross-platform (Windows paths with spaces safe). CI entry: npm run sweep:role-home:e2e
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_TOTP_HEX = 'eab95095c004f245721ba0fa7ebf82d5dc73';
const port = (process.env.VISUAL_QA_PORT || '8012').trim();
const slug = (process.env.TENANT_SLUG || 'demo-school').trim();
const loginUrl = `http://127.0.0.1:${port}/t/${slug}/authentication/login/`;
const dbFile =
  process.env.DB_FILE ||
  path.join(repo, `db_playwright_role_home_${process.pid}.sqlite3`);
const demoUsers = [
  'demo.admin',
  'demo.teacher',
  'demo.parent',
  'demo.student',
];

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
    if (code === 200) {
      stableOk += 1;
      if (stableOk >= 3) {
        return;
      }
    } else {
      stableOk = 0;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  console.error(`run_role_home_e2e: server not ready at ${loginUrl}`);
  process.exit(1);
}

const py = resolvePython();
const baseEnv = {
  DB_FILE: dbFile,
  REDIS_URL: '',
  RMC_FORCE_DB_SESSIONS: '1',
  SECURE_SSL_REDIRECT: '0',
  DEBUG: '1',
  CSRF_COOKIE_SECURE: '0',
  SESSION_COOKIE_SECURE: '0',
  RMC_DEPLOYMENT_PROFILE: 'online',
  OBSERVABILITY_METRICS_BACKEND: 'noop',
  ALLOWED_HOSTS:
    process.env.ALLOWED_HOSTS ||
    '127.0.0.1,localhost,testserver,runmycampus.com,.runmycampus.com',
  MULTI_TENANT_BASE_DOMAIN: process.env.MULTI_TENANT_BASE_DOMAIN || 'runmycampus.com',
  VISUAL_QA_PORT: port,
  VISUAL_QA_TOTP_HEX_KEY:
    process.env.VISUAL_QA_TOTP_HEX_KEY ||
    process.env.VISUAL_QA_TOTP_HEX ||
    DEFAULT_TOTP_HEX,
  TENANT_SWEEP_PASSWORD: process.env.TENANT_SWEEP_PASSWORD || 'Test1234',
};

console.log('=== role-home e2e: migrate ===');
if (process.env.RMC_E2E_KEEP_DB !== '1' && fs.existsSync(dbFile)) {
  try {
    fs.unlinkSync(dbFile);
    console.log(`removed stale e2e db ${dbFile}`);
  } catch (err) {
    console.warn(`could not remove stale e2e db: ${err}`);
  }
}
runSync(['manage.py', 'migrate', '--noinput'], baseEnv);

console.log(`=== role-home e2e: ensure developer sandbox (${slug}) ===`);
runSync(
  [
    'manage.py',
    'ensure_developer_sandbox_tenant',
    `--school-slug=${slug}`,
    `--password=${baseEnv.TENANT_SWEEP_PASSWORD}`,
  ],
  baseEnv,
);

console.log('=== role-home e2e: seed TOTP for demo personas ===');
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
users = ${JSON.stringify(demoUsers)}
for username in users:
    user = get_user_model().objects.filter(username=username).first()
    if not user:
        raise SystemExit(f'demo tenant user missing: {username}')
    user.is_active = True
    if username.endswith('.admin'):
        user.is_staff = True
    user.save()
    TOTPDevice.objects.filter(user=user).delete()
    device = TOTPDevice.objects.create(user=user, name='e2e-playwright', confirmed=True)
    device.key = key
    device.save()
    print(f'Seeded TOTP e2e-playwright for {username}')
`.trim(),
  ],
  baseEnv,
);

const artifactDir = path.join(repo, 'artifacts', 'role-home-e2e');
fs.mkdirSync(artifactDir, { recursive: true });
const serverLog = path.join(artifactDir, 'runserver.log');
const serverLogFd = fs.openSync(serverLog, 'a');

console.log(`=== role-home e2e: runserver 127.0.0.1:${port} ===`);
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
    console.error(`run_role_home_e2e: runserver exited ${code}`);
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

const cleanupDb = () => {
  if (process.env.RMC_E2E_KEEP_DB === '1') {
    return;
  }
  if (fs.existsSync(dbFile)) {
    try {
      fs.unlinkSync(dbFile);
    } catch (_e) {
      /* ignore — Windows may still hold the handle briefly */
    }
  }
};

process.on('exit', () => {
  stopServer();
  cleanupDb();
});
for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    stopServer();
    process.exit(130);
  });
}

await waitForServer();

console.log('=== role-home e2e: visual sweep ===');
const tenantOnly = process.env.ROLE_SWEEP_TENANT_ONLY || '1';
const sweep = spawnSync(
  process.execPath,
  [path.join(repo, 'scripts', 'run_role_home_visual_sweep.mjs')],
  {
    cwd: repo,
    env: {
      ...process.env,
      ...baseEnv,
      ROLE_SWEEP_TENANT_ONLY: tenantOnly,
    },
    stdio: 'inherit',
    shell: false,
  },
);

stopServer();

if (sweep.status === 0) {
  console.log('ROLE_HOME_VISUAL_SWEEP_E2E_PASS');
}
process.exit(sweep.status ?? 1);
