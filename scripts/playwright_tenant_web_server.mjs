#!/usr/bin/env node
/**
 * Cross-platform Playwright webServer launcher for tenant phase1/phase2 E2E.
 * Resolves a Python interpreter (venv-first) and execs run_playwright_tenant_e2e_server.py.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const script = path.join(repo, 'scripts', 'run_playwright_tenant_e2e_server.py');

function resolvePython() {
  if (process.env.VISUAL_QA_PYTHON) {
    return process.env.VISUAL_QA_PYTHON;
  }
  const candidates = [
    path.join(repo, '.venv', 'Scripts', 'python.exe'),
    path.join(repo, '.venv', 'bin', 'python'),
    'python3',
    'python',
    'py',
  ];
  for (const candidate of candidates) {
    if (candidate.includes(path.sep) || candidate.endsWith('.exe')) {
      if (fs.existsSync(candidate)) {
        return candidate;
      }
      continue;
    }
    return candidate;
  }
  return 'python';
}

const py = resolvePython();
const args =
  py === 'py' ? ['-3', script] : [script];

// Never use shell:true — repo paths contain spaces on Windows and break spawn quoting.
const child = spawn(py, args, {
  cwd: repo,
  env: process.env,
  stdio: 'inherit',
  shell: false,
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

child.on('error', (err) => {
  console.error('playwright_tenant_web_server: failed to start Python', err);
  process.exit(1);
});
