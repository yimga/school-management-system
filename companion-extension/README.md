# RunMyCampus Companion (browser extension)

Manifest V3 helper that reads roster data from the SIS browser tab the
operator is already logged into, sealed-box encrypts it client-side, and
uploads it to the RunMyCampus migration cloud.

The extension never embeds credentials and never performs programmatic
login to a SIS. It only reads the DOM of the operator's own
authenticated session. See `docs/COMPANION_SIBLINGS.md` (in the main
repo) for the full architectural boundary.

## Local development

Prerequisites: Node.js ≥ 18.18 and npm.

```bash
cd companion-extension
npm install
npm run typecheck     # tsc --noEmit on src/ + tests/
npm run test          # vitest run (jsdom; chrome.storage mock)
npm run build         # vite build → dist/
```

### Load unpacked in Chrome

1. Open `chrome://extensions/`.
2. Toggle **Developer mode** on (top-right).
3. Click **Load unpacked** and choose `companion-extension/dist/`
   (after running `npm run build`).
4. Pin the extension to the toolbar. Click its icon to open the popup.

### Watch mode

`npm run dev` runs Vite in watch mode. The Chrome runtime does NOT
hot-reload extension code automatically — click the reload arrow in
`chrome://extensions/` after each rebuild.

## Layout

```
companion-extension/
├── manifest.json            MV3 manifest (host_permissions for 6 SIS vendors)
├── popup.html               Popup shell (loads src/popup/popup.ts)
├── package.json             npm scripts + deps
├── tsconfig.json            strict TS, ES2022, ~/lib aliases
├── vite.config.ts           multi-entry build (popup/background/content)
├── vitest.config.ts         jsdom + tests/setup.ts
├── .eslintrc.cjs            strict @typescript-eslint rules
├── .prettierrc              shared format
├── src/
│   ├── lib/                 reusable modules (tenant_switcher, …)
│   ├── popup/               popup controllers
│   ├── content/             content scripts (injected into SIS tabs)
│   ├── background/          MV3 service-worker
│   └── vendors/             per-vendor DOM extractors (PowerSchool, …)
└── tests/
    ├── setup.ts             chrome.storage mock for jsdom
    └── *.test.ts            vitest specs
```

`src/content/`, `src/background/`, and `src/vendors/` may not yet exist
in this checkout — the vite config declares the entries so that adding
the corresponding files starts producing bundles without any further
config changes. The build will fail gracefully (`ENOENT`) until you add
at least a stub `service_worker.ts` / `content_script.ts` if you wire
them in manifest.json. To build popup-only, comment out the
`background` + `content` keys in `vite.config.ts::rollupOptions.input`
and the corresponding manifest entries.

## Trust model

- Vendor `host_permissions` are for legitimate content-script DOM
  reading of the **operator's own authenticated tab**. The extension
  never embeds, captures, or replays SIS credentials.
- All upload payloads to RunMyCampus are sealed-box encrypted client
  side using the server's per-tenant X25519 public key, fetched via the
  anonymous `/companion/server-pubkey/?tenant=<slug>` endpoint. Verify
  the displayed fingerprint against the Django admin's out-of-band copy
  before signing the MAA.
- See `docs/SECURITY_KEYS.md` (in the main repo) for full key model.
