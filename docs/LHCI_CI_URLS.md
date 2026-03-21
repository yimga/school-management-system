# Lighthouse CI — multiple URLs (N10)

`lighthouserc.cjs` collects:

1. **`LHCI_URL`** — primary absolute URL (required in GitHub `vars` when workflow runs).
2. **`LHCI_URLS_EXTRA`** — optional comma-separated **full URLs** on the **same origin** as `LHCI_URL`, e.g.  
   `https://staging.example.com/marketing/,https://staging.example.com/portal/parent/`
3. **`LHCI_AUTO_EXTRAS`** — set to `1` to append the **recommended path bundle** from the same origin as `LHCI_URL` (see `lighthouserc.cjs` and [LHCI_STAGING_GITHUB_VARS.md](LHCI_STAGING_GITHUB_VARS.md)). Merges with `LHCI_URLS_EXTRA` and dedupes.

GitHub Actions workflow `.github/workflows/lighthouse-ci.yml` passes:

- `vars.LHCI_URL`
- `vars.LHCI_URLS_EXTRA` (optional)
- `vars.LHCI_AUTO_EXTRAS` (optional; `1` enables auto bundle)
- `vars.LHCI_STRICT_N10` — set to `1` to fail on stricter performance / LCP thresholds (`lighthouserc.cjs`).

Local:

```bash
export LHCI_URL="http://127.0.0.1:8000/marketing/"
export LHCI_URLS_EXTRA="http://127.0.0.1:8000/portal/parent/"
npx lhci autorun --config=./lighthouserc.cjs
```

**Staging GitHub vars:** [LHCI_STAGING_GITHUB_VARS.md](LHCI_STAGING_GITHUB_VARS.md).
