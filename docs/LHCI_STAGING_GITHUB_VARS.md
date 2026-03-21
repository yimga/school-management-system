# Lighthouse CI — GitHub repository variables (staging)

Set these in **GitHub → Repository → Settings → Secrets and variables → Actions → Variables** (not secrets unless you prefer).

| Variable | Example | Purpose |
|----------|---------|---------|
| `LHCI_URL` | `https://staging.runmycampus.com/marketing/` | Primary Lighthouse URL (must be reachable from GitHub runners). |
| `LHCI_URLS_EXTRA` | See **recommended bundle** below | Extra full URLs (comma-separated, **no spaces** after commas). Same origin as `LHCI_URL`. Expand once staging is stable. |
| `LHCI_STRICT_N10` | `1` or empty | When `1`, `lighthouserc.cjs` uses **error** level and tighter performance / LCP budgets. |
| `LHCI_AUTO_EXTRAS` | `1` or empty | When `1`, Lighthouse collects the **recommended same-origin URL bundle** (marketing, platform, parent portal, bulk-capture, verify, support) in addition to `LHCI_URL` and `LHCI_URLS_EXTRA` — see `lighthouserc.cjs`. Use when staging is stable so you can shorten or drop manual `LHCI_URLS_EXTRA`. |

**Workflow:** `.github/workflows/lighthouse-ci.yml` runs only when `vars.LHCI_URL` is non-empty (`if: vars.LHCI_URL != ''`).

**Local parity:**

```bash
export LHCI_URL="https://your-staging.example/marketing/"
export LHCI_URLS_EXTRA="https://your-staging.example/portal/parent/"
export LHCI_AUTO_EXTRAS=1
export LHCI_STRICT_N10=1
npx @lhci/cli@0.14.x autorun --config=./lighthouserc.cjs
```

See also [LHCI_CI_URLS.md](LHCI_CI_URLS.md) and [PERFORMANCE_BUDGETS.md](PERFORMANCE_BUDGETS.md).

## Recommended `LHCI_URLS_EXTRA` when staging is stable

Use your real staging host in place of `https://staging.runmycampus.com`. Order: marketing proof pages first, then high-traffic portal shells (no auth required paths only if listed in `lighthouserc.cjs` / workflow; staff-only URLs may 302 on CI — prefer public or marketing URLs).

**Starter set (comma-separated, no spaces):**

```text
https://staging.runmycampus.com/marketing/,
https://staging.runmycampus.com/platform/,
https://staging.runmycampus.com/education-operating-system/,
https://staging.runmycampus.com/portal/parent/,
https://staging.runmycampus.com/portal/teacher/bulk-capture/,
https://staging.runmycampus.com/verify/,
https://staging.runmycampus.com/support/
```

**Ops / hub smoke (optional; may require session — confirm runner can reach or omit):**

```text
https://staging.runmycampus.com/accounts/ops-hub/
```

Trim or extend to match what your Lighthouse workflow can access without login. Document any auth-gated URLs in [LHCI_CI_URLS.md](LHCI_CI_URLS.md).

## RUM (optional)

Real-user metrics ingestion is documented in [RUM_HOOK.md](RUM_HOOK.md). RUM is independent of LHCI but complements synthetic runs once `RUM_INGEST_KEY` is set.
