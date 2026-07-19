# Lighthouse A+ runbook (#2 Tenant Experience / #17 Performance)

**Bar:** every key surface scores **≥ 98** on Performance (and Accessibility ≥ 98 where asserted).  
**Honesty:** this runbook + `npm run lighthouse:a-plus` are **scaffolding**. A committed score artifact under `docs/generated/` with real ≥98 numbers is required before #2/#17 can claim A+. Never invent scores.

---

## 1. Prerequisites

1. Django serving the target host(s) locally or on staging.
2. Node deps installed (`npm ci` or `npm install`).
3. Optional: `@lhci/cli@0.13.x` (pulled via `npx` in npm scripts).

| Surface | Host / URL pattern | Config |
|---------|-------------------|--------|
| Marketing / public | `http://127.0.0.1:8000/` or staging origin | `lighthouserc.cjs` / `lighthouserc.js` |
| Tenant portal | tenant subdomain login + portal paths | `lighthouserc-tenant.cjs` |
| Operator / manager | `manager.runmycampus.com` (mapped to local) | set `LHCI_URL` + extras (see below) |

Related docs: [PERFORMANCE_BUDGET.md](PERFORMANCE_BUDGET.md), [LHCI_CI_URLS.md](LHCI_CI_URLS.md), [LHCI_STAGING_GITHUB_VARS.md](LHCI_STAGING_GITHUB_VARS.md).

---

## 2. Key URL sets (A+ checklist)

### Tenant (metric #2)

With Django on `VISUAL_QA_PORT` (default `8124`) and tenant slug `demo-school`:

| Role | Path |
|------|------|
| Login | `/authentication/login/` |
| Portal home | `/portal/` |
| Parent | `/portal/parent/` |
| Teacher | `/portal/teacher/` |
| Offline shell | `/offline/` |

```bash
# Boots tenant host + runs lighthouserc-tenant.cjs
npm run lighthouse:tenant

# Same with assert minScore 0.98 (fails if below — does not invent scores)
LHCI_TENANT_STRICT=1 npm run lighthouse:tenant:strict
```

### Operator / marketing (metric #17)

```bash
export LHCI_URL="http://127.0.0.1:8000/"
export LHCI_AUTO_EXTRAS=1
# Optional extras: manager landing, control-plane skeleton routes
export LHCI_URLS_EXTRA="http://127.0.0.1:8000/marketing/,http://manager.runmycampus.com:8000/"
npm run lighthouse
```

### Documented A+ stub (does not fake scores)

```bash
npm run lighthouse:a-plus
```

This prints the exact command matrix and exits **non-zero** unless a committed ≥98 artifact already exists (see §4). It never writes fabricated scores.

---

## 3. Recommended local sequence

1. Start Django with the correct `ALLOWED_HOSTS` / tenant host mapping.
2. Warm caches once (hit login + one portal page in a browser).
3. Run tenant LHCI (`npm run lighthouse:tenant`).
4. Run marketing/operator LHCI (`npm run lighthouse` with `LHCI_URL` set).
5. If all category scores are ≥ 0.98, **record** them (next section).

---

## 4. Committing evidence (required for A+)

Create or update:

`docs/generated/lighthouse_a_plus_scores.json`

Shape (example — replace with real LHCI output):

```json
{
  "generated_at": "2026-07-19T00:00:00Z",
  "commit_sha": "<git rev-parse HEAD>",
  "min_score_required": 98,
  "surfaces": [
    {
      "id": "tenant_login",
      "url": "http://127.0.0.1:8124/authentication/login/",
      "performance": 98,
      "accessibility": 98,
      "source": "lhci"
    },
    {
      "id": "tenant_portal",
      "url": "http://127.0.0.1:8124/portal/",
      "performance": 98,
      "accessibility": 99,
      "source": "lhci"
    },
    {
      "id": "operator_home",
      "url": "http://manager.runmycampus.com:8000/",
      "performance": 98,
      "accessibility": 98,
      "source": "lhci"
    }
  ]
}
```

Rules:

- Scores must come from a real LHCI / Chrome Lighthouse run.
- At least one tenant URL and one operator/marketing URL.
- Every listed `performance` (and `accessibility` when present) must be **≥ 98**.
- `verify_lighthouse_scaffold.py` reads this file; absence → `EXTERNAL_LIGHTHOUSE_SCORE_REQUIRED`.

---

## 5. Repo verifier

```bash
python scripts/verify_lighthouse_scaffold.py
python scripts/verify_lighthouse_scaffold.py --json
```

| Result | Meaning |
|--------|---------|
| `LIGHTHOUSE_SCAFFOLD_PASS` | Runbook + npm/LHCI config present |
| `EXTERNAL_LIGHTHOUSE_SCORE_REQUIRED` | No committed artifact with all scores ≥98 (honest; not a scaffold failure) |

---

## 6. EXTERNAL residual (honest)

Until §4 artifact exists with real ≥98 scores:

- **#2 Tenant Experience** — Lighthouse ≥98 EXTERNAL
- **#17 Performance** — Lighthouse ≥98 EXTERNAL

CI workflows `lighthouse-ci.yml` / `lighthouse-tenant-ci.yml` may warn below 0.98; they do **not** substitute for a committed score ledger.
