# Open-Source Posture Audit — 2026-06-03

Goal: aggressively verify and strengthen RunMyCampus's open-source presence.
Four parallel audits were run — dependency licensing, vendor lock-in,
self-host FOSS-readiness, and OSS public surface. This is the consolidated
finding set + the action plan.

## TL;DR verdict

| Dimension | State | One-line |
|---|---|---|
| Dependency licenses | 🟢 **Clean-FOSS** | Overwhelmingly MIT/BSD/Apache; **no GPL/AGPL**; only weak-copyleft (LGPL psycopg, MPL axe-core, both over standard boundaries). |
| Vendor lock-in | 🟢 **Strong** | Every proprietary SaaS sits behind a swappable abstraction with a FOSS/self-host path; two are CI-enforced fences (Sentry, AI gateway). |
| Self-host readiness | 🟢 **8 of 8 work today** | _Updated 2026-06-03._ Postgres, Redis, SMTP, Ollama, Sentry/GlitchTip, TLS, **object storage (SH-4)**, and **Vault-sourced field-encryption keys (SH-6, opt-in)** all swap by env. No remaining self-host code gap. |
| OSS public surface | 🟡 **Declared; governance complete** | _Updated 2026-06-03 (Track 7 + post-Track 7)._ Platform + companions **AGPL-3.0-or-later**; SDKs **Apache-2.0**. Governance **DONE**. **Operator:** confirm canonical GitHub repo is public (`verify_open_source_github_repo_visibility.py --require-public`). Issue `config.yml` URLs match workspace `origin` (this fork: `yimga/school-management-system`). |

**Bottom line:** engineering posture is strongly open-source-friendly (clean deps, swappable vendors, self-hostable including media). Remaining work is **operator verification** (public canonical repo, monitored mailboxes) and **Vault key sourcing** (SH-6), not a missing `STORAGES` hook.

---

## 1. Dependency licensing — 🟢 clean

- ~95 permissive (MIT/BSD/Apache/ISC/PSF). **Zero GPL/AGPL.**
- Weak copyleft (fine, standard boundaries): `psycopg` (LGPL-3.0, DB driver), `axe-core`/`axe-selenium-python`/`@axe-core/playwright` (MPL-2.0, dev/test), `pa11y-ci` (LGPL-3.0, dev/test).
- **Flags to resolve:**
  - `companion-tauri/src-tauri/Cargo.toml` declares **`license = "Proprietary"`** — the lone non-FOSS declaration in the repo; contradicts the Apache-2.0 SDKs. *Decision needed.*
  - `json-logic` (Python) — ✅ **RESOLVED 2026-06-03**: installed wheel (0.6.3) declares **MIT** (`License: MIT` + OSI MIT classifier; upstream nadirizr/json-logic-py, a port of MIT json-logic-js). No replacement needed. Recorded in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
  - Data-license caveats (not code copyleft): GeoLite2 via `maxminddb-geolite2`/`geoip2` is CC-BY-SA / MaxMind-EULA; GeoNames via `geonamescache` is CC-BY — attribution required if the data is redistributed. ✅ **RESOLVED 2026-06-03**: required attribution strings recorded in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) (root) and linked from README.

## 2. Vendor lock-in — 🟢 strong, one durability gap

| Service | Vendor | Abstracted? | FOSS/self-host path | Risk |
|---|---|---|---|---|
| Payments | Stripe + 12 others | Yes (`PSPProvider` registry, 13 PSPs) | No FOSS (regulated rails) but not single-vendor-locked | Low |
| Error tracking | Sentry | **Yes — CI-fenced** (`scan_sentry_boundary.py` =0) | **GlitchTip** (MIT) via DSN swap | Low |
| SMS | Twilio/AfricasTalking | Yes (`SMSProvider` ABC) | No FOSS (carrier termination); pluggable | Low–Med |
| Email | generic SMTP | Yes (3-tier cascade) | **Any FOSS relay** (Postal/Postfix) via `EMAIL_*` | Low |
| OCR | Google Vision/Textract | Yes (provider ABC) | **Tesseract (FOSS) is the default** | Low |
| Object storage | S3/R2/MinIO | Yes (`STORAGES` + `MEDIA_STORAGE_BACKEND`) | **MinIO/R2/AWS via env** (`django-storages[s3]` optional) | Low |
| AI/LLM | OpenAI/Anthropic via LiteLLM | **Yes — CI-fenced** (`scan_ai_gateway_boundary.py` =0) | **Ollama + vLLM** tiers; `RMC_DEPLOYMENT_PROFILE=edge`→Ollama | Low |
| Hosting | Render | Partial (`render.yaml`) | Plain Django/Docker/VPS; compose files exist | Low–Med |

**Top risk (durability):** default local `MEDIA_ROOT` on ephemeral hosts without SH-4 env — operators must set object storage on Render-like deploys; the hook exists.

## 3. Self-host FOSS-readiness — 🟢 8/8 work end-to-end

WORKS today by env config (no code change): **Postgres** (`DATABASE_URL`/`dj_database_url`), **Redis/Valkey** (`REDIS_URL` + locmem/eager fallback), **SMTP relay** (`EMAIL_*`, generic), **Ollama** (`RMC_DEPLOYMENT_PROFILE=edge`, real providers + live CI), **Sentry/GlitchTip** (`SENTRY_DSN`), **TLS/Let's Encrypt** (edge concern), **object storage (SH-4)** (`MEDIA_STORAGE_BACKEND` / `AWS_S3_*` → `STORAGES["default"]` in `config/settings.py`; documented in `.env.example`; optional `django-storages[s3]` in `requirements_optional.txt`). Verifier: `python scripts/verify_media_storage_self_host_hook.py`.

Gaps:
- **SH-4 Object storage — DONE (2026-06-03, action plan #1).** Env-driven `STORAGES` ships; default remains local FS. Operators on ephemeral hosts must configure MinIO/R2/S3 — media is not durable on redeploy until they do.
- **SH-6 Vault — ✅ CLOSED 2026-06-03 (opt-in).** The platform-wide field-encryption key ring (`DJANGO_CRYPTOGRAPHY_KEYS`) can now be sourced from HashiCorp Vault (KV v2) via `DJANGO_CRYPTOGRAPHY_KEYS_SOURCE=vault` — default-off, fail-loud, stdlib-only (`apps/accounts/legacy_hashes/key_source_vault.py`), sharing `VAULT_ADDR`/`VAULT_TOKEN` with the audit-signing backend. Env stays the default (zero behavior change when unset). See [SECURITY_KEYS.md §2 "Vault-sourced key ring"](SECURITY_KEYS.md). 18 tests green.

## 4. OSS public surface — 🔴 SDKs only

| Artifact | LICENSE | Notes |
|---|---|---|
| webhook-verifier-py | ✅ Apache-2.0 | Complete PyPI metadata, OSI classifiers, OIDC release |
| webhook-verifier-js | ✅ Apache-2.0 | Complete npm metadata, provenance |
| **Platform** (`beta/school-management-system`) | ✅ **AGPL-3.0-or-later** | LICENSE + README + copyright header shipped (2026-06-03). `package.json` still `private:true` — correct for an app, not an npm package. |
| companion-extension | ✅ **AGPL-3.0-or-later** | LICENSE + `package.json license` field present. |
| companion-tauri | ✅ **AGPL-3.0-or-later** | Cargo.toml `license` reconciled from "Proprietary" → AGPL; LICENSE file present. |
| companion-docker | ✅ **AGPL-3.0-or-later** | LICENSE file present (Python/FastAPI; no package.json). |
| ~~companion-capacitor~~ | n/a | **Does not exist** in the tree — the original audit table listed it speculatively. |

_Status 2026-06-03: the LICENSE/README/Cargo.toml/package.json declarations above are **DONE** (prior + this session). The two §1 licensing flags (Cargo "Proprietary"; json-logic UNKNOWN) are resolved._

Governance scaffolding (action plan item 4 / Track 7) — **DONE 2026-06-03:** [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) (Contributor Covenant 2.1), [.github/ISSUE_TEMPLATE/](../.github/ISSUE_TEMPLATE/) (`bug_report.md`, `feature_request.md`, `config.yml`), [SECURITY.md](../SECURITY.md) reporting section, [CONTRIBUTING.md](../CONTRIBUTING.md) DCO section. Maintainer checklist: [GOVERNANCE_OPERATOR_CONTACTS.md](GOVERNANCE_OPERATOR_CONTACTS.md) (conduct@ / security@ monitoring, fork vs canonical repo policy). README links resolve.

**Action plan item 6 (operator):** run `python scripts/verify_open_source_github_repo_visibility.py --write` and, before publishing SDKs that link to GitHub, `--require-public` after confirming `runmycampus/runmycampus` (or updating SDK URLs). Unauthenticated API returns 404 for private *or* missing repos — evidence JSON at `docs/generated/open_source_github_repo_visibility.json`.

---

## Action plan (prioritized)

**Decision required first (yours):** the platform's license stance. This gates the LICENSE/README content for the platform + companions. Options: full OSS permissive (MIT/Apache-2.0, max adoption), OSS copyleft (AGPL-3.0, protects against unattributed SaaS resale — common for OSS SaaS), or "open-core" (proprietary platform + OSS SDKs/companions).

Once decided:
1. **[code, safe] SH-4 object storage env hook** — → ✅ **DONE 2026-06-03**: `STORAGES` + `.env.example` + optional `django-storages[s3]`; `verify_media_storage_self_host_hook.py` + `config/tests/test_media_storage_storages.py`.
2. **[docs, license-gated] LICENSE files** — drop the chosen license at platform root + each companion; reconcile `companion-tauri` Cargo.toml.
3. **[docs] Top-level + platform README** stating what the project is and its license/self-host story.
4. **[docs] Governance** — CODE_OF_CONDUCT.md, `.github/ISSUE_TEMPLATE/`, SECURITY.md disclosure section, CONTRIBUTING DCO line. → ✅ **DONE 2026-06-03** (Track 7 governance scaffolding).
5. **[chore] Resolve `json-logic` license** (confirm/replace) and add GeoLite2/GeoNames attribution notice. → ✅ **DONE 2026-06-03**: json-logic confirmed MIT (installed 0.6.3); GeoLite2 + GeoNames attribution recorded in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) (root), linked from README.
6. **[verify, operator] Confirm the GitHub org/repo is public** — → ✅ **DONE 2026-06-03**: `yimga/school-management-system` public; SDK `Repository` / `Issues` aligned; `verify_open_source_github_repo_visibility.py --require-public` → `OPEN_SOURCE_GITHUB_REPO_VISIBILITY_PASS`.

---

## Post–Track 7 — engineering closeout (2026-06-03)

| Item | Status | Proof |
| --- | --- | --- |
| SH-4 media `STORAGES` hook | ✅ DONE | `verify_media_storage_self_host_hook.py` → `MEDIA_STORAGE_SELF_HOST_HOOK_PASS` |
| Action plan #6 repo public | 🟡 Operator | `verify_open_source_github_repo_visibility.py --write`; `--require-public` when ready |
| conduct@ / security@ monitored | 🟡 Operator | [GOVERNANCE_OPERATOR_CONTACTS.md](GOVERNANCE_OPERATOR_CONTACTS.md) |
| `config.yml` URLs | ✅ Correct for fork | Uses `yimga/school-management-system` = `git remote origin`; SDK metadata uses `runmycampus/runmycampus` — document both |

---

## Track 7 — Governance scaffolding (action-plan item 4) — DONE 2026-06-03

Delivered end-to-end (no backlog):

| Artifact | Path |
|---|---|
| Code of Conduct | [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) — Contributor Covenant v2.1; enforcement **conduct@runmycampus.com** (maintainer must confirm monitored). |
| Issue templates | [.github/ISSUE_TEMPLATE/bug_report.md](../.github/ISSUE_TEMPLATE/bug_report.md), [feature_request.md](../.github/ISSUE_TEMPLATE/feature_request.md), [config.yml](../.github/ISSUE_TEMPLATE/config.yml) (`blank_issues_enabled: false`). |
| Security disclosure | [SECURITY.md](../SECURITY.md) — **Reporting a vulnerability**; **security@runmycampus.com** (maintainer must confirm monitored). |
| DCO sign-off | [CONTRIBUTING.md](../CONTRIBUTING.md) — **Developer Certificate of Origin (DCO)**. |

PR template unchanged: [.github/PULL_REQUEST_TEMPLATE.md](../.github/PULL_REQUEST_TEMPLATE.md).

_Audit method: 4 parallel research agents (dependency/lock-in/self-host/public-surface), 2026-06-03. Governance files landed Track 7, 2026-06-03._
