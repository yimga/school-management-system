# Self-Hosting & External Dependencies Backlog

**Created:** 2026-06-03
**Purpose:** Single source of truth for (1) infrastructure we intend to
**self-host on free / open-source software**, and (2) capabilities that
**cannot be obtained for free** and are therefore tracked as **external
dependencies** (each needs a budget decision, not just engineering).

**Guiding principle (from the operator):** prefer open-source / community
tooling and the free tier wherever possible. Anything that cannot be free is
listed under § 2 as an external dependency so it is never an invisible surprise.

---

## § 1 — Self-hosting backlog (free / FOSS targets)

These can run on free or open-source software. Most still need *somewhere* to
run; where the only cost is a small VPS, that VPS is itself listed in § 2.

| # | Item | FOSS tool | Status | Notes |
|---|------|-----------|--------|-------|
| SH-1 | **Outbound email relay** | **Postal** (MIT) — self-hosted SendGrid equivalent: SMTP + API + DKIM + bounce/complaint/suppression + tracking | **Backlog** | Plugs into the existing Django `EMAIL_*` config with zero code change (becomes `EMAIL_HOST`). **Cannot run on Render** (port 25 blocked) → requires the port-25 VPS in § 2 (EXT-1). Runbook to be written: `docs/SELF_HOSTED_EMAIL_POSTAL.md`. Interim: free provider tier (see EXT-2). Alternatives considered + rejected: raw Postfix/Haraka (no bounce/DKIM/tracking layer — Gmail/Yahoo bulk rules require it). |
| SH-2 | **Database (Postgres)** | PostgreSQL (FOSS) | **Backlog / watch** | Render free Postgres **expires ~90 days after creation**. Self-hosting Postgres is free software but needs a host with a persistent disk (→ EXT-1). Until then: Render free PG (web service currently `plan: standard`, DB `plan: free`). |
| SH-3 | **Task broker / cache (Redis)** | Redis / Valkey (FOSS) | **Backlog** | Render Redis is `plan: free` (limited memory/connections). No broker on free tier is why provisioning uses the **synchronous fallback** (see the `_do_provision_tracked` fix, 2026-06-02). Self-host Redis/Valkey needs a host (→ EXT-1). |
| SH-4 | **Object storage for tenant media** | **MinIO** (AGPL, S3-compatible) self-host | **Backlog — CONFIRMED issue** | `MEDIA_ROOT` is the **local filesystem** (`config/settings.py`) and **`render.yaml` declares NO persistent `disk:`** → uploaded media (logos, documents, photos) is **ephemeral and lost on every redeploy**. Fix: **Cloudflare R2** (10 GB free, S3-compatible) now, or **MinIO** self-host on EXT-1 later. Highest-priority durability gap in this list. |
| SH-5 | **AI inference** | **Ollama** (MIT) on the `edge` deployment profile | **Available (free)** | Already supported: `RMC_DEPLOYMENT_PROFILE=edge` → Ollama. The paid alternative (LiteLLM → cloud models) is EXT-6. No action needed to stay free; quality/latency tradeoff. |
| SH-6 | **Secrets / KMS** | **HashiCorp Vault OSS** (self-host, free) or the built-in Fernet shim | **Available (free)** | `VAULT_*` env supported; the internal Fernet shim (needs `DJANGO_CRYPTOGRAPHY_KEYS`) works without Vault. The paid path is a cloud **HSM** (EXT-7), which is already a deferred item. |
| SH-7 | **Error monitoring** | Self-host **GlitchTip** (Sentry-compatible, MIT) or **Sentry** free tier | **Optional** | `SENTRY_DSN` is optional. Sentry's free tier is usually enough; GlitchTip is the FOSS self-host if needed. |
| SH-8 | **TLS certificates** | **Let's Encrypt** (free) | **Available (free)** | No paid cert needed for web/email/Postal. |

---

## § 2 — External dependencies (CANNOT be free — budget required)

Each of these has **no free production path**. They are dependencies on an
outside vendor and/or recurring money. Tracked here so they are explicit.

| # | Dependency | Why it can't be free | Cheapest real option | Free interim / mitigation | Status |
|---|-----------|----------------------|----------------------|---------------------------|--------|
| **EXT-1** | **VPS that allows outbound port 25** (to host Postal / Postgres / Redis / MinIO) | **Every free tier blocks port 25** (Oracle, GCP, AWS, Azure, Fly, Render) to prevent spam. Direct mail delivery is impossible without it. | **Hetzner** ~€4/mo (unblocks port 25 on request); OVH / Contabo / Netcup similar | None for *direct* sending. A free Oracle VPS could host Postal but must relay via a provider on 587 — which removes the only benefit (unlimited direct send). | **Backlog (blocks SH-1)** |
| **EXT-2** | **Transactional email — interim** | Provider free tiers are capped | Brevo **300/day free** (9k/mo); Mailjet 200/day; SMTP2GO 1k/mo; Resend 3k/mo | The free tier *is* the mitigation — covers activation/transactional at current scale until SH-1 is stood up | **Recommended now** |
| **EXT-3** | **SMS gateway** (alerts, attendance, 2FA) | SMS requires carrier termination — there is **no FOSS substitute** and **no free production SMS**; per-message cost | Twilio / **AfricasTalking** (providers already integrated: `apps/communication/providers/sms_*.py`); Termii for Africa | Email-only for non-critical notifications; SMS off until budgeted | **External — pay per message** |
| **EXT-4** | **Payment gateway** (tuition, billing) | Card processing is regulated; gateways charge **per-transaction fees** (no free path) | **Stripe** (already integrated — `apps/billing/embedded_checkout.py`); Paystack/Flutterwave for Africa | None — required to collect money; fees come out of transactions (no monthly cost) | **External — transaction fees** |
| **EXT-5** | **Domain name** (`runmycampus.com`) | Registration is inherently paid (annual) | ~$10–15/yr at registrar | Already owned | **Owned** |
| **EXT-6** | **Cloud AI (LiteLLM → hosted models)** | Hosted LLM API usage is metered | LiteLLM proxy + provider keys (`LITELLM_*`) | **Use Ollama (SH-5) for free** on the edge profile | **Optional — free alt exists** |
| **EXT-7** | **Cloud HSM** (audit root-key signing) | Hardware-backed key custody is a paid managed service | AWS KMS / Azure Key Vault / GCP KMS / HashiCorp Vault Cloud | **Vault OSS self-host (SH-6)** or the Fernet shim cover it for now | **Deferred (free alt exists)** |
| **EXT-8** | **OCR** (document/ID extraction) | Google Cloud Vision (`GOOGLE_CLOUD_VISION_API_KEY`) is metered | Google Cloud Vision (pay per call) | **Self-host Tesseract** (Apache-2, FOSS) — quality tradeoff | **Optional — free alt exists** |
| **EXT-9** | **Object storage @ scale** (if media outgrows free) | S3/managed object storage is metered beyond free tiers | AWS S3 / Backblaze B2 | **Cloudflare R2 10 GB free** or **MinIO self-host (SH-4)** | **Free path exists for now** |
| **EXT-10** | **Persistent compute beyond free** | Free tiers sleep / expire / are CPU-capped | Render `standard` (web already on it) / a VPS (EXT-1) | Free tier with the SSE/thread caps already shipped | **Partially paid (web = standard)** |
| **EXT-11** | **Code-signing certificates** (companion desktop apps) | OS vendors require paid certs | Apple Developer $99/yr; Windows OV/EV cert | Cosign **keyless** (free) for the Docker sibling only | **Deferred** |
| **EXT-12** | **OAuth partner credentials** (Schoology / D2L live) | Issued only via vendor partner programs | Vendor partner account (may have cost/approval) | Static-Bearer + sandbox covered; live needs real creds | **External — vendor-gated** |

---

## Recommended sequencing

1. **Now (free):** EXT-2 — set Render `EMAIL_*` to Brevo free tier so activation
   email works at $0. (Phase 1 of the email plan.)
2. **When email volume > ~300/day, or when ready to self-host:** EXT-1 (Hetzner
   ~€4/mo) + SH-1 (Postal) + `docs/SELF_HOSTED_EMAIL_POSTAL.md` runbook + DNS
   (SPF/DKIM/DMARC/PTR) + IP warm-up.
3. **Before the Render free Postgres 90-day expiry:** decide SH-2 (self-host on
   EXT-1) vs Render paid DB.
4. **Media durability check:** confirm whether a Render persistent disk is
   attached; if not, do SH-4 (R2 free tier first, MinIO later).
5. **Stay free indefinitely where alternatives exist:** SH-5 (Ollama), SH-6
   (Vault/Fernet), SH-7 (GlitchTip/Sentry free), EXT-8 (Tesseract).
6. **Pay only when the feature is needed:** EXT-3 (SMS), EXT-4 (payments),
   EXT-7 (HSM), EXT-11 (code-signing), EXT-12 (OAuth partner).

> Note: a single **EXT-1 VPS (~€4/mo)** unlocks SH-1, SH-2, SH-3, and SH-4 at
> once (Postal + Postgres + Redis + MinIO on one box). That €4/mo is the single
> highest-leverage spend for going fully self-hosted.
