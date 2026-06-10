#!/usr/bin/env node
/**
 * Batch 1701 — boot Django on 8013, wait for health, run phase1/phase2 Playwright.
 * Cross-platform (Windows paths with spaces safe).
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_TOTP_HEX = 'eab95095c004f245721ba0fa7ebf82d5dc73';
const port = (process.env.VISUAL_QA_TENANT_PHASE_PORT || process.env.VISUAL_QA_PORT || '8013').trim();
const slug = (process.env.TENANT_SLUG || 'demo-school').trim();
const loginUrl = `http://127.0.0.1:${port}/t/${slug}/authentication/login/`;

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
    req.setTimeout(4000, () => {
      req.destroy();
      resolve(0);
    });
  });
}

async function waitForServer(maxSeconds = 180) {
  for (let i = 0; i < maxSeconds; i += 1) {
    const code = await probe(loginUrl);
    if (code >= 200 && code < 500) {
      return;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  console.error(`run_tenant_phase_e2e: server not ready at ${loginUrl}`);
  process.exit(1);
}

const py = resolvePython();
const baseEnv = {
  REDIS_URL: '',
  RMC_FORCE_DB_SESSIONS: '1',
  SECURE_SSL_REDIRECT: '0',
  DEBUG: '1',
  CSRF_COOKIE_SECURE: '0',
  SESSION_COOKIE_SECURE: '0',
  VISUAL_QA_PORT: port,
  VISUAL_QA_TENANT_PHASE_PORT: port,
  VISUAL_QA_TOTP_HEX_KEY:
    process.env.VISUAL_QA_TOTP_HEX_KEY ||
    process.env.VISUAL_QA_TOTP_HEX ||
    DEFAULT_TOTP_HEX,
  E2E_TENANT_USER: process.env.E2E_TENANT_USER || 'demo.admin',
};

console.log('=== tenant phase e2e: migrate ===');
runSync(['manage.py', 'migrate', '--noinput'], baseEnv);

console.log('=== tenant phase e2e: seed demo-school ===');
runSync(
  [
    'manage.py',
    'seed_demo_tenant_users',
    `--school-slug=${slug}`,
    `--password=${process.env.E2E_TENANT_PASSWORD || 'Test1234'}`,
  ],
  baseEnv,
);

console.log('=== tenant phase e2e: seed demo.admin TOTP (MFA verify) ===');
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
username = os.environ.get('E2E_TENANT_USER', 'demo.admin')
user = get_user_model().objects.filter(username=username).first()
if not user:
    raise SystemExit(f'demo tenant user missing: {username}')
user.is_staff = True
user.is_superuser = True
user.is_active = True
user.save(update_fields=['is_staff', 'is_superuser', 'is_active'])
TOTPDevice.objects.filter(user=user).delete()
device = TOTPDevice.objects.create(user=user, name='e2e-playwright', confirmed=True)
device.key = os.environ.get('VISUAL_QA_TOTP_HEX_KEY', '${DEFAULT_TOTP_HEX}')
device.save()
print(f'Seeded TOTP e2e-playwright for {username}')
`.trim(),
  ],
  {
    ...baseEnv,
    E2E_TENANT_USER: process.env.E2E_TENANT_USER || 'demo.admin',
    VISUAL_QA_TOTP_HEX_KEY:
      process.env.VISUAL_QA_TOTP_HEX_KEY ||
      process.env.VISUAL_QA_TOTP_HEX ||
      DEFAULT_TOTP_HEX,
  },
);

console.log(`=== tenant phase e2e: runserver 127.0.0.1:${port} ===`);
const serverLog = path.join(repo, 'artifacts', 'residual-closure-1701', 'runserver-phase.log');
fs.mkdirSync(path.dirname(serverLog), { recursive: true });
const serverLogFd = fs.openSync(serverLog, 'a');
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
    console.error(`run_tenant_phase_e2e: runserver exited ${code}`);
  }
});

process.on('exit', () => {
  if (!serverExited && server.pid) {
    try {
      process.kill(server.pid);
    } catch (_e) {
      /* ignore */
    }
  }
});

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    if (server.pid) {
      try {
        process.kill(server.pid);
      } catch (_e) {
        /* ignore */
      }
    }
    process.exit(130);
  });
}

await waitForServer();

console.log('=== tenant phase e2e: Playwright phase1 + phase2 ===');
const pwCli = path.join(repo, 'node_modules', '@playwright', 'test', 'cli.js');
const pw = spawnSync(
  process.execPath,
  [
    pwCli,
    'test',
    'tests/e2e/phase1-architecture-navigation.spec.js',
    'tests/e2e/phase2-portal-navigation.spec.js',
    '--project=tenant-phase-chromium',
    '--workers=1',
  ],
  {
    cwd: repo,
    env: {
      ...process.env,
      ...baseEnv,
      RMC_E2E_EXTERNAL_SERVER: '1',
    },
    stdio: 'inherit',
    shell: false,
  },
);

if (server.pid) {
  try {
    process.kill(server.pid);
  } catch (_e) {
    /* ignore */
  }
}

if (pw.status === 0) {
  console.log('TENANT_PHASE_E2E_PASS');
}
process.exit(pw.status ?? 1);
