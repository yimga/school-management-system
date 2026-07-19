#!/usr/bin/env node
/**
 * A+ Lighthouse command matrix stub (#2 / #17).
 *
 * Documents how to collect >=98 scores on tenant + operator URLs.
 * Does NOT invent scores. Exits 0 only when a committed artifact already
 * proves >=98; otherwise exits 2 with EXTERNAL_LIGHTHOUSE_SCORE_REQUIRED.
 *
 * Usage: npm run lighthouse:a-plus
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const artifact = path.join(repo, 'docs', 'generated', 'lighthouse_a_plus_scores.json');

console.log(`
Lighthouse A+ command matrix (does not fake scores)
===================================================
See: docs/LIGHTHOUSE_A_PLUS_RUNBOOK.md

1) Tenant (login + portal):
   npm run lighthouse:tenant
   LHCI_TENANT_STRICT=1 npm run lighthouse:tenant:strict

2) Marketing / public:
   LHCI_URL=http://127.0.0.1:8000/ LHCI_AUTO_EXTRAS=1 npm run lighthouse

3) Operator (manager host mapped locally):
   LHCI_URL=http://manager.runmycampus.com:8000/ npm run lighthouse

4) Record real scores into:
   docs/generated/lighthouse_a_plus_scores.json
`);

const verify = spawnSync(
  process.platform === 'win32' ? 'python' : 'python3',
  [path.join(repo, 'scripts', 'verify_lighthouse_scaffold.py')],
  { cwd: repo, stdio: 'inherit', shell: false },
);
if (verify.status !== 0 && verify.status != null) {
  process.exit(verify.status);
}

if (!fs.existsSync(artifact)) {
  console.error(
    'EXTERNAL_LIGHTHOUSE_SCORE_REQUIRED: no committed score artifact yet.',
  );
  process.exit(2);
}

// Re-check via verifier JSON for scores_a_plus_proven
const jsonRun = spawnSync(
  process.platform === 'win32' ? 'python' : 'python3',
  [path.join(repo, 'scripts', 'verify_lighthouse_scaffold.py'), '--json'],
  { cwd: repo, encoding: 'utf8', shell: false },
);
try {
  const report = JSON.parse(jsonRun.stdout || '{}');
  if (report.scores_a_plus_proven) {
    console.log('LIGHTHOUSE_A_PLUS_SCORES_PROVEN');
    process.exit(0);
  }
} catch {
  /* fall through */
}
console.error(
  'EXTERNAL_LIGHTHOUSE_SCORE_REQUIRED: artifact present but scores <98 or incomplete.',
);
// ASCII-only messages for Windows consoles.
process.exit(2);
