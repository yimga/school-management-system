#!/usr/bin/env node
/**
 * Boot Django, seed wizard kernels, and run unified-wizard-framework Playwright
 * with live tenant + manager auth (no storageState skip path).
 *
 *   npm run test:e2e:unified-wizard-framework
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DEFAULT_TOTP_HEX = 'eab95095c004f245721ba0fa7ebf82d5dc73';
const port = (process.env.VISUAL_QA_WIZARD_PORT || process.env.VISUAL_QA_TENANT_PHASE_PORT || '8014').trim();
const slug = (process.env.TENANT_SLUG || 'demo-school').trim();
const loginUrl = `http://127.0.0.1:${port}/t/${slug}/authentication/login/`;
const e2eDbDir = path.join(repo, '.django_test_dbs');
const e2eDbFile = path.join(
  e2eDbDir,
  process.env.RMC_WIZARD_E2E_DB_FILE || 'unified-wizard-e2e.sqlite3',
);

function prepareE2eDatabase() {
  fs.mkdirSync(e2eDbDir, { recursive: true });
  if (process.env.RMC_E2E_FRESH_DB === '1' || process.env.RMC_E2E_FRESH_DB === 'true') {
    try {
      fs.unlinkSync(e2eDbFile);
    } catch (_e) {
      /* missing */
    }
  }
}

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
  console.error(`run_unified_wizard_framework_e2e: server not ready at ${loginUrl}`);
  process.exit(1);
}

const py = resolvePython();
const managerPassword = process.env.VISUAL_QA_PASSWORD || process.env.E2E_LOGIN_PASSWORD || 'VisualQaPass123!';
const tenantPassword = process.env.E2E_TENANT_PASSWORD || 'Test1234';
const totpHex =
  process.env.VISUAL_QA_TOTP_HEX_KEY ||
  process.env.VISUAL_QA_TOTP_HEX ||
  DEFAULT_TOTP_HEX;

const baseEnv = {
  REDIS_URL: '',
  RMC_FORCE_DB_SESSIONS: '1',
  SECURE_SSL_REDIRECT: '0',
  DEBUG: '1',
  CSRF_COOKIE_SECURE: '0',
  SESSION_COOKIE_SECURE: '0',
  DB_FILE: e2eDbFile,
  ALLOWED_HOSTS:
    process.env.ALLOWED_HOSTS ||
    '127.0.0.1,localhost,testserver,runmycampus.com,.runmycampus.com',
  VISUAL_QA_PORT: port,
  VISUAL_QA_TENANT_PHASE_PORT: port,
  VISUAL_QA_WIZARD_PORT: port,
  VISUAL_QA_TOTP_HEX_KEY: totpHex,
  E2E_TENANT_USER: process.env.E2E_TENANT_USER || 'demo.admin',
  E2E_TENANT_PASSWORD: tenantPassword,
  VISUAL_QA_USERNAME: process.env.VISUAL_QA_USERNAME || 'visualqa_admin',
  VISUAL_QA_PASSWORD: managerPassword,
  E2E_LOGIN_USER: process.env.E2E_LOGIN_USER || 'visualqa_admin',
  E2E_LOGIN_PASSWORD: managerPassword,
};

console.log('=== unified wizard e2e: migrate ===');
prepareE2eDatabase();
runSync(['manage.py', 'migrate', '--noinput'], baseEnv);

console.log('=== unified wizard e2e: seed manager visualqa_admin ===');
runSync(
  [
    '-c',
    `
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
U = get_user_model()
password = os.environ.get('VISUAL_QA_PASSWORD', 'VisualQaPass123!')
u, _ = U.objects.get_or_create(
    username='visualqa_admin',
    defaults={
        'email': 'visualqa@runmycampus.com',
        'is_staff': True,
        'is_superuser': True,
        'is_active': True,
    },
)
u.is_staff = True
u.is_superuser = True
u.is_active = True
u.set_password(password)
u.save()
print('Seeded visualqa_admin for manager wizard E2E')
`.trim(),
  ],
  baseEnv,
);

console.log('=== unified wizard e2e: ensure demo-school sandbox ===');
runSync(
  [
    'manage.py',
    'ensure_developer_sandbox_tenant',
    `--school-slug=${slug}`,
    `--password=${tenantPassword}`,
  ],
  baseEnv,
);

console.log('=== unified wizard e2e: seed visualqa_admin TOTP (manager MFA) ===');
runSync(
  [
    '-c',
    `
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice
username = os.environ.get('VISUAL_QA_USERNAME', 'visualqa_admin')
user = get_user_model().objects.filter(username=username).first()
if not user:
    raise SystemExit(f'manager user missing: {username}')
user.is_staff = True
user.is_superuser = True
user.is_active = True
user.last_security_posture_review_at = timezone.now()
user.save(update_fields=['is_staff', 'is_superuser', 'is_active', 'last_security_posture_review_at'])
TOTPDevice.objects.filter(user=user).delete()
device = TOTPDevice.objects.create(user=user, name='e2e-playwright', confirmed=True)
device.key = os.environ.get('VISUAL_QA_TOTP_HEX_KEY', '${DEFAULT_TOTP_HEX}')
device.save()
print(f'Seeded TOTP e2e-playwright for {username}')
`.trim(),
  ],
  baseEnv,
);

console.log('=== unified wizard e2e: seed demo.admin TOTP ===');
runSync(
  [
    '-c',
    `
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth import get_user_model
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice
username = os.environ.get('E2E_TENANT_USER', 'demo.admin')
user = get_user_model().objects.filter(username=username).first()
if not user:
    raise SystemExit(f'demo tenant user missing: {username}')
user.is_staff = True
user.is_superuser = True
user.is_active = True
user.last_security_posture_review_at = timezone.now()
user.save(update_fields=['is_staff', 'is_superuser', 'is_active', 'last_security_posture_review_at'])
TOTPDevice.objects.filter(user=user).delete()
device = TOTPDevice.objects.create(user=user, name='e2e-playwright', confirmed=True)
device.key = os.environ.get('VISUAL_QA_TOTP_HEX_KEY', '${DEFAULT_TOTP_HEX}')
device.save()
print(f'Seeded TOTP e2e-playwright for {username}')
`.trim(),
  ],
  baseEnv,
);

console.log('=== unified wizard e2e: seed operational wizard kernels ===');
runSync(['manage.py', 'seed_operational_wizard_kernels', `--school=${slug}`], baseEnv);

console.log(`=== unified wizard e2e: runserver 127.0.0.1:${port} ===`);
const serverLog = path.join(repo, 'artifacts', 'unified-wizard-e2e', 'runserver.log');
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
    console.error(`run_unified_wizard_framework_e2e: runserver exited ${code}`);
  }
});

const shutdown = () => {
  if (!serverExited && server.pid) {
    try {
      process.kill(server.pid);
    } catch (_e) {
      /* ignore */
    }
  }
};
process.on('exit', shutdown);
for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    shutdown();
    process.exit(130);
  });
}

await waitForServer();

const tenantBase = `http://127.0.0.1:${port}/t/${slug}`;
const managerBase = `http://manager.runmycampus.com:${port}`;

console.log('=== unified wizard e2e: Playwright (live auth) ===');
const pwCli = path.join(repo, 'node_modules', '@playwright', 'test', 'cli.js');
const pw = spawnSync(
  process.execPath,
  [
    pwCli,
    'test',
    'tests/e2e/unified-wizard-framework.spec.js',
    '--project=unified-wizard-chromium',
    '--workers=1',
  ],
  {
    cwd: repo,
    env: {
      ...process.env,
      ...baseEnv,
      DB_FILE: e2eDbFile,
      RMC_E2E_EXTERNAL_SERVER: '1',
      RMC_WIZARD_E2E_LIVE: '1',
      WIZARD_TENANT_BASE_URL: tenantBase,
      WIZARD_OPERATOR_BASE_URL: managerBase,
      MANAGER_BASE_URL: managerBase,
      PLAYWRIGHT_TENANT_BASE_URL: tenantBase,
    },
    stdio: 'inherit',
    shell: false,
  },
);

shutdown();

if (pw.status === 0) {
  console.log('UNIFIED_WIZARD_FRAMEWORK_E2E_PASS');
}
process.exit(pw.status ?? 1);
