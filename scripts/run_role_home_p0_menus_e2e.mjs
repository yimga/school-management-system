#!/usr/bin/env node
/** Windows-safe entry: tenant P0 menu + homes E2E (batch 1728). */
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const result = spawnSync(
  process.execPath,
  [path.join(repo, 'scripts', 'run_role_home_e2e.mjs')],
  {
    cwd: repo,
    env: {
      ...process.env,
      ROLE_SWEEP_TENANT_ONLY: '1',
      ROLE_SWEEP_P0_MENUS: '1',
    },
    stdio: 'inherit',
    shell: false,
  },
);
process.exit(result.status ?? 1);
