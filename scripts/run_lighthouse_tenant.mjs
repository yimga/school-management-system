#!/usr/bin/env node
/**
 * Boot Django on tenant subdomain host, then run Lighthouse CI (lighthouserc-tenant.cjs).
 * Usage: npm run lighthouse:tenant
 * Strict A+: LHCI_TENANT_STRICT=1 npm run lighthouse:tenant
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
if (process.env.npm_lifecycle_event === 'lighthouse:tenant:strict') {
  process.env.LHCI_TENANT_STRICT = '1';
}
const port = (process.env.VISUAL_QA_TENANT_PHASE_PORT || process.env.VISUAL_QA_PORT || '8124').trim();
const slug = (process.env.TENANT_SLUG || 'demo-school').trim();
const loginUrl = `http://127.0.0.1:${port}/authentication/login/`;

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

function probeTenantUrl(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return Promise.resolve(0);
  }
  const hostHeader = parsed.hostname;
  const port = parsed.port || (parsed.protocol === 'https:' ? '443' : '80');
  return new Promise((resolve) => {
    const req = http.request(
      {
        hostname: '127.0.0.1',
        port,
        path: `${parsed.pathname}${parsed.search}`,
        headers: { Host: hostHeader },
      },
      (res) => {
        res.resume();
        resolve(res.statusCode ?? 0);
      },
    );
    req.on('error', () => resolve(0));
    req.setTimeout(4000, () => {
      req.destroy();
      resolve(0);
    });
    req.end();
  });
}

function probe(url) {
  if (url.includes('/authentication/login')) {
    return probeTenantUrl(`http://${slug}.runmycampus.com:${port}/authentication/login/`);
  }
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
    if (code === 200) {
      return;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  console.error(`run_lighthouse_tenant: server not ready at ${loginUrl}`);
  process.exit(1);
}

const py = resolvePython();
const baseEnv = {
  REDIS_URL: '',
  RMC_FORCE_DB_SESSIONS: '1',
  SECURE_SSL_REDIRECT: '0',
  DEBUG: '1',
  LOGIN_POW_ENABLED: '0',
  CSRF_COOKIE_SECURE: '0',
  SESSION_COOKIE_SECURE: '0',
  ALLOWED_HOSTS: '127.0.0.1,localhost,testserver,runmycampus.com,.runmycampus.com',
  MULTI_TENANT_BASE_DOMAIN: 'runmycampus.com',
  VISUAL_QA_PORT: port,
  VISUAL_QA_TENANT_PHASE_PORT: port,
  TENANT_SLUG: slug,
};

console.log('=== lighthouse tenant: migrate ===');
runSync(['manage.py', 'migrate', '--noinput'], baseEnv);

console.log('=== lighthouse tenant: ensure demo-school ===');
runSync(['manage.py', 'ensure_developer_sandbox_tenant', `--school-slug=${slug}`], baseEnv);

console.log(`=== lighthouse tenant: runserver 127.0.0.1:${port} ===`);
const server = spawn(py, ['manage.py', 'runserver', `127.0.0.1:${port}`, '--noreload'], {
  cwd: repo,
  env: { ...process.env, ...baseEnv, PYTHONUNBUFFERED: '1' },
  stdio: 'inherit',
  shell: false,
});

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

const lhciEnv = {
  ...process.env,
  ...baseEnv,
  LHCI_TENANT_URL: loginUrl,
  LHCI_TENANT_HOST: `${slug}.runmycampus.com`,
  LHCI_TENANT_AUTO_EXTRAS: process.env.LHCI_TENANT_AUTO_EXTRAS ?? "0",
};

console.log(`=== lighthouse tenant: LHCI (${loginUrl}) ===`);
const lhci = spawnSync(
  process.platform === 'win32' ? 'npx.cmd' : 'npx',
  ['@lhci/cli@0.13.x', 'autorun', '--config=lighthouserc-tenant.cjs'],
  { cwd: repo, env: lhciEnv, stdio: 'inherit', shell: true },
);

killServer();
if (lhci.status !== 0) {
  process.exit(lhci.status ?? 1);
}
