# AI deployment posture (canonical)

Single reference for how RunMyCampus routes **live AI**, **guided fallback**, and **offline school operations**. Execution checklist: `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` §11.4 batch **1370**.

## Three layers (do not conflate)

| Layer | Runs where | Needs internet to school server? | Technology |
| --- | --- | --- | --- |
| **School operations (offline mode)** | Teacher/staff browser (PWA + service worker) | Only to sync queued writes | Dexie + `/api/offline/delta/` — **not LLM** |
| **Live AI** | Django app server (Render or LAN hub) | Yes, for new AI answers | `services.ai_gateway` tier chain |
| **Guided fallback** | Django (rules + KB + topology) | Yes for first load; cached UI may show hints | `services.ai_guided_fallback` |

**Never** install Ollama on each teacher laptop. **Never** expect full AI on a device with zero connectivity to the tenant origin.

## Deployment profiles (`RMC_DEPLOYMENT_PROFILE`)

| Profile | Typical host | Default gateway tiers (when env set) |
| --- | --- | --- |
| `online` (default) | Render SaaS | `litellm` → `ollama` → `rules` if `LITELLM_PROXY_URL` set; else `ollama` → `rules` |
| `edge` | School LAN hub | `ollama` → `rules` |
| `hybrid` | Render + optional `RMC_HUB_BASE_URL` | Per serving origin: Render uses configured cloud/server tiers; the hub origin may use local Ollama |

Implementation: `services/ai_deployment_posture.py` — merged into `services/ai_gateway._task_tiers()`.

Override per task only via Django `settings.AI_GATEWAY_TASK_TIERS` (dict), not env strings.

`RMC_HUB_BASE_URL` is a browser/service-worker application failover target. It
does not let a Render process reach a private `192.168.x.x` Ollama endpoint.
Cross-network AI failover requires the browser to use the hub origin or a
separately secured tunnel/proxy.

## Recommended production profile (Option A)

Default for **Render SaaS** until usage or quality data says otherwise:

| Choice | Value | Why |
| --- | --- | --- |
| Routing | One cloud model + built-in tier fallback | `litellm` → `ollama` → `rules` — no per-task or proxy router required at launch |
| Model | `gpt-5.4-mini` | Stable cost/latency for copilot, help, support, and short operator answers |
| Fallback | `AI_ALLOW_RULES_FALLBACK=1` | Guided help when cloud is down or over budget |
| OpenAI direct | `LITELLM_PROXY_URL=https://api.openai.com` | API host — not `platform.openai.com` (login UI only) |

Per-task tier splits (`AI_GATEWAY_TASK_TIERS`), self-hosted
LiteLLM-compatible routing, and the tenant premium cap
(`AI_PREMIUM_DAILY_CAP_PER_TENANT`) are implemented. Automatic quality-based
model escalation is intentionally not enabled: it would spend money and move
data across tiers without an explicit tenant policy. Governed fallback remains
the safer default.

## Render SaaS (production default)

```bash
RMC_DEPLOYMENT_PROFILE=online
RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION=1
AI_GATEWAY_ENABLED=1
AI_ALLOW_RULES_FALLBACK=1
LITELLM_PROXY_URL=https://api.openai.com
LITELLM_API_KEY=...
LITELLM_MODEL=gpt-5.4-mini
```

- **Do not** rely on Ollama inside a Render web dyno for primary inference.
- **Do** set LiteLLM to any OpenAI-compatible proxy (LiteLLM, Azure OpenAI, provider gateway). For OpenAI direct use `https://api.openai.com` — **not** `https://platform.openai.com` (that URL is the human login dashboard only).
- UI surfaces posture via AI Center, copilot health pill, `/api/ai/health/`.

Verify repo contracts: `python scripts/verify_render_online_ai_posture.py`

## LAN hub (edge)

See `docs/LOCAL_HUB_MODE.md` and `docs/OLLAMA_OPERATIONS_AND_UPDATES.md` for `ollama serve`, Modelfile, and `verify_ollama_live.py`.

## Hybrid AI proposal audit (2026-06-07)

The four supplied proposal texts were audited against the current code and SOTs.
They contain two substantially duplicated concepts. No pasted snippet is
approved for direct implementation.

### Decision matrix

| Proposal element | Decision | Reason |
| --- | --- | --- |
| Cloud model with deterministic fallback | **Keep** | Already implemented through the governed gateway, timeout/circuit-breaker logic, and rules fallback. |
| Ollama on a school LAN hub | **Keep** | Already supported by the `edge` profile when Django serves the request from the hub. |
| Direct browser call to cloud/Ollama providers | **Reject** | Bypasses gateway permissions, PII policy, audit, rate limits, budgets, and provider-health controls. |
| CDN-imported browser SLM as an offline guarantee | **Reject** | First use needs network; CDN/runtime/model caching is not guaranteed; conflicts with self-hosted asset and CSP posture. |
| Hardcoded `192.168.1.100` or `localhost` routing | **Reject** | Not tenant-safe, not portable, and cannot be reached from Render without explicit network infrastructure. |
| Browser OCR/LLM writes Django rows while disconnected | **Reject** | A disconnected browser cannot write the server database. It must create validated queue records and reconcile through existing sync/idempotency contracts. |
| On-device OCR UI | **Plan first** | Narrow, deterministic, and already listed as a product gap; use a self-hosted worker/runtime and queue structured proposals for human review. |
| Browser SLM | **Repository verified; disabled by default** | Same-origin, checksum-pinned worker integration exists for reversible drafting. A model pack and real-device evidence are still required for pilot activation. |
| Universal `100dvh` and five-column rewrite | **Reject as AI scope** | Layout changes require page-family evidence and accessibility testing; they are not an AI routing requirement. |
| RLS installed from `post_migrate` signal | **Reject** | RLS belongs in reviewed migrations and the existing tenant-context contract, not ad hoc runtime DDL. |

### Platform operating model: Linux / AWS / Salesforce / Shopify, locally

The product goal is not to imitate four user interfaces. It is to combine their
durable platform properties while ensuring each school experiences a system
that is locally governed:

| Reference property | RunMyCampus interpretation |
| --- | --- |
| **Linux** | Open, portable, composable foundations across x86_64 and ARM64; no device, model, database-provider, or cloud lock-in. |
| **AWS** | A governed set of infrastructure primitives, deployment profiles, regional cells, capacity evidence, observability, and explicit failure modes. |
| **Salesforce** | Tenant metadata, permissions, policy, vocabulary, workflow, and localization alter behavior without customer-specific code forks. |
| **Shopify** | Versioned capability packages and marketplace extensions activate through stable contracts, permissions, audit, rollback, and compatibility checks. |
| **Always local** | Language, terminology, jurisdiction, calendar, grading, currency, workflow, residency, connectivity, and support posture resolve per tenant and remain visible in the experience. |

The executable contract is
`config/sovereign_platform_contract.json`, enforced by
`python scripts/verify_sovereign_platform_contract.py`.

### Research re-audit addendum (2026-06-08)

The follow-up research names real open-source technologies, but it converts
capabilities into guarantees that the upstream projects do not make. Adopt the
technologies only through the existing platform boundaries and evidence gates.

| Research claim | Re-audit decision | Platform action |
| --- | --- | --- |
| Transformers.js / ONNX Runtime Web makes a full browser SLM universally offline | **Conditionally valid** | Browser inference is possible, but model download, storage quota, execution-provider support, RAM, and performance vary by device. Keep it optional, self-hosted, feature-detected, and non-blocking. |
| A 4-bit model has an exact fixed RAM requirement and therefore an 8 GB Raspberry Pi is production-ready | **Unproven as a deployment guarantee** | Model file size is not peak process RAM or usable throughput. Certify each hardware/model/context combination with concurrent-load, thermal, restart, and latency evidence. Prefer a 16 GB-class edge host for a multi-service campus hub; treat an 8 GB Pi as a constrained single-model pilot. |
| PostgreSQL RLS makes cross-tenant leaks mathematically impossible | **Reject the absolute claim; keep RLS** | Retain migration-managed, default-deny, `FORCE ROW LEVEL SECURITY` policies using canonical `app.current_school_id`. Owners, `BYPASSRLS`, bad policies, missing table coverage, and incorrect context remain risks that tests and least privilege must control. Do not introduce `request.jwt.claim.tenant_id`. |
| PgBouncer transaction pooling can preserve the current per-request tenant session state | **Blocked with current implementation** | Current code uses session-level `SET` / `RESET`; PgBouncer documents these as incompatible with transaction pooling. Use a session/unpooled endpoint today. A future transaction-pooling profile requires transaction-local context, request-wide transaction boundaries, worker/task coverage, and adversarial isolation tests. |
| LWW-element-set CRDTs eliminate collisions and overwrite hazards for every domain | **Reject the universal claim; keep typed CRDTs** | CRDTs guarantee deterministic convergence for their defined merge semantics, not preservation of every concurrent intent. Keep LWW only for approved low-risk scalar fields; use OR-set/G-counter/grow-only operation logs where appropriate; keep grades, money, identity, and permissions server-authoritative or in manual review. |
| `sqlite-vss`, Faiss, or Chroma should become the edge RAG store | **Reject parallel stores by default** | Reuse `AIEmbeddingStore`, `services.ai_memory`, tenant filters, and the existing JSON-cosine/pgvector paths. If a SQLite edge benchmark proves an index is needed, evaluate `sqlite-vec` behind the same repository contract; `sqlite-vss` is no longer actively developed and `sqlite-vec` is still pre-v1. |
| ResizeObserver automatically self-heals clipping with zero lag | **Use only as measurement and telemetry** | CSS container/media queries, wrapping, row-detail drawers, and accessibility remain primary. ResizeObserver may detect component size changes and emit bounded telemetry; it must not globally shrink fonts or mutate layout in a feedback loop. |
| Multi-agent OCR + LLM grading should run autonomously at the edge | **Reject autonomous grading** | OCR may propose structured marks. A teacher must confirm the student match, score, rubric, and final write. Do not use a general multimodal model as the authoritative grade engine. |
| Whisper + Piper provide a complete offline voice layer | **Candidate, not committed** | Pilot speech-to-text and text-to-speech as accessibility features behind language/device support checks. Benchmark target languages and hardware, review model and GPL distribution obligations, and retain text controls. |
| Cloud, LAN, and browser tiers can provide identical behavior | **Reject** | Preserve one task contract and comparable audit metadata, but disclose capability and quality differences. Deterministic fallback must remain useful when live generation is unavailable. |
| Generic hardware should replace Raspberry-Pi-specific deployment rules | **Adopt** | Hardware support is capability-based across x86_64 and ARM64. Detect effective CPU, memory, storage, architecture, and container limits; never infer production capacity from a device name. |
| `os.cpu_count() * 2 + 1` should automatically configure web workers | **Reject** | CPU count ignores memory, container quotas, blocking mix, and database limits. The profiler may recommend a bounded starting point, but load evidence and operator configuration remain authoritative. |
| LocMem cache is the optimized generic-hardware default | **Reject for multi-worker production** | LocMem is process-local and creates inconsistent cache state across workers. Preserve the existing cache abstraction and use Redis/Valkey when shared cache semantics are required. |
| Hardcode PostgreSQL on loopback port 6432 with two-minute persistent connections | **Reject** | Connection topology remains environment-driven. Port 6432 implies a pooler but does not prove its mode is compatible with tenant session state. |
| QR/RFID ambient capture should replace routine clicks | **Keep through existing contracts** | Device-agnostic proximity attendance, QR attendance, POS credentials, and boarding taps already exist. Extend adapters and consent/audit evidence; do not create a new telemetry table or bypass canonical APIs. |

Primary implementation references:

- Transformers.js and ONNX Runtime Web:
  <https://huggingface.co/docs/transformers.js/> and
  <https://onnxruntime.ai/docs/tutorials/web/>
- PostgreSQL RLS and PgBouncer pooling behavior:
  <https://www.postgresql.org/docs/current/ddl-rowsecurity.html> and
  <https://www.pgbouncer.org/features.html>
- CRDT convergence definition:
  <https://arxiv.org/abs/1805.06358>
- ResizeObserver processing model:
  <https://www.w3.org/TR/resize-observer/>
- SQLite vector extension status:
  <https://github.com/asg017/sqlite-vss> and
  <https://github.com/asg017/sqlite-vec>

### Updated execution plan

1. **P0 - preserve one architecture and close unsafe documentation.**
   - Keep all AI calls behind `services.ai_helpers` and `services.ai_gateway`.
   - Keep `app.current_school_id`, reviewed RLS migrations, and existing
     default-deny/FORCE-RLS verification. Do not add a second tenant GUC.
   - Use session/unpooled PostgreSQL connections for schema and RLS profiles
     until a transaction-local tenant-context design is implemented and tested.
   - Keep `AIEmbeddingStore` as the shared RAG contract; do not add an
     independently synchronized Faiss, Chroma, or `sqlite-vss` database.
   - Enforce `config/sovereign_platform_contract.json` so future phases retain
     the Linux/AWS/Salesforce/Shopify platform properties and tenant-local
     resolution without creating code forks.

2. **P1 - certify the campus edge appliance before expanding models.**
   - Define supported capability profiles rather than promising one device:
     constrained pilot, standard edge, and high-capacity edge across x86_64 and
     ARM64.
   - Detect effective CPU quota, usable memory, free storage, architecture, and
     container limits. Recommendations are bounded starting points, never
     automatic production worker settings.
   - Benchmark one model at a time through Ollama using representative prompts,
     context sizes, two-to-five concurrent users, cold starts, sustained heat,
     memory pressure, power loss, restart recovery, and queue backpressure.
   - Publish a signed model manifest with exact model digest, license, intended
     tasks, context cap, measured latency, RAM high-water mark, and rollback.
   - Add multiple resident models only when task quality evidence justifies the
     operational cost. "Multi-agent" is not an acceptance criterion.

   **P1 implementation status (2026-06-08): DONE for repo scope.**
   `services.edge_hardware` now produces capability profiles from effective
   CPU, memory, storage, architecture, and container limits without changing
   worker settings. `config/edge_model_catalog.json` owns task restrictions,
   resource admission, rollback, and measurable pilot limits. The
   `certify_edge_ai` command records Ollama digest/runtime data, concurrent
   latency, failures, a body checksum, and an HMAC signature. On the available
   x86_64 standard-edge host, `qwen2.5:1.5b` passed the pilot performance gate
   (4/4, concurrency 2, p50 6.2 s, p95 6.4 s); `llama3.1:8b` failed latency
   (4/4 functional, p50 40.9 s, p95 61.7 s). Both remain
   `production_certified=false` until sustained thermal, power-loss recovery,
   rollback, and task-quality drills are completed on the deployment hardware.
   Evidence is stored under `var/evidence/edge/`.

3. **P2 - ship the lowest-risk offline intelligence first: OCR proposals.**
   - Build the marks-entry camera/import experiment in a worker using
     self-hosted assets and the existing correction-store direction.
   - Produce a structured proposal with confidence and source coordinates.
   - Require teacher confirmation and queue the accepted mutation through the
     existing offline envelope, idempotency, tenant validation, and conflict
     review paths. No model writes a final grade directly.

   **P2 implementation status (2026-06-08): DONE for repo scope.**
   The server upload path now always stages a proposal, rejects scores outside
   0-20, and requires an explicit checked teacher attestation; the former
   confidence-based auto-write branch is removed. The editable preview is
   correctly inside its confirmation form. A pinned, self-hosted
   `tesseract.js@7.0.0` worker can process PNG/JPG/WebP images in the browser,
   retain line confidence and source bounding boxes, preserve existing marks in
   delta mode, and fill highlighted gradebook cells without submitting. The
   teacher's existing Save action is the only bridge to the canonical encrypted
   grade WAL/outbox and manual conflict policy. Vendored assets have SHA-256
   checksums. A localhost-only Chromium smoke recognized
   `STD001 12 13 14` at confidence 83 with all non-local requests blocked.

4. **P3 - make local RAG portable without creating a second truth store.**
   - Export signed, tenant-scoped knowledge bundles from the canonical ingest
     pipeline and import them into the hub's existing Django data contract.
   - Preserve document IDs, embedding-model version, chunk hashes, scope,
     retention, and deletion tombstones across cloud and edge.
   - Use JSON cosine for small corpora, pgvector for production PostgreSQL, and
     evaluate `sqlite-vec` only after measured query latency requires it.

   **P3 implementation status (2026-06-08): DONE for repo scope.**
   `AIEmbeddingStore` now owns portable document identity, embedding
   model/dimensions, retention, source timestamps, and active/tombstone
   lifecycle. Signed tenant bundles use deterministic JSON, SHA-256 body
   checksums, HMAC-SHA256, exact school binding, atomic idempotent import, and
   newer-tombstone replay protection. Retrieval excludes deleted, expired,
   cross-tenant, and incompatible-model rows. Export/import commands move only
   tenant rows; platform-global knowledge is never smuggled into a tenant
   bundle. JSON cosine remains the small/offline fallback and the existing
   pgvector migration/index commands remain the production path. See
   [TENANT_RAG_BUNDLES.md](TENANT_RAG_BUNDLES.md).

   **Local-first synchronization prerequisite status (2026-06-08): DONE for
   repo scope.** A versioned canonical policy registry now governs aliases,
   causal LWW, append-only entities, server-authoritative entities, and manual
   review. Protected grade, finance, identity, permission, message, behavior,
   and wallet policies cannot be weakened by caller overrides. The generic
   CRDT endpoint accepts only approved low-risk namespaces, binds actor identity
   to the authenticated user/device, serializes tenant state updates, and uses
   replay-safe G-counter and order-independent OR-set semantics. See
   [LOCAL_FIRST_SYNC_SEMANTICS.md](LOCAL_FIRST_SYNC_SEMANTICS.md).

5. **P4 - pilot voice as accessibility, not as a required control surface.**
   - Compare Whisper Tiny/Base and Piper on target languages, noisy classrooms,
     low-end hardware, and assistive-technology workflows.
   - Require push-to-talk, visible transcript/edit controls, consent, retention
     limits, and a complete keyboard/text path.
   **P4 repository status (2026-06-08): DONE.** Authenticated tenant endpoints,
   explicit one-action consent, push-to-talk, editable transcripts, no-store
   TTS, endpoint host allowlists, language/size caps, content-free audit
   metadata, and complete text fallback are implemented. The feature remains
   off until a LAN service is configured and cannot advance beyond repository
   verification without signed pilot evidence. See
   [LOCAL_VOICE_ACCESSIBILITY.md](LOCAL_VOICE_ACCESSIBILITY.md).

6. **P5 - run a governed browser-inference spike last.**
   - Self-host pinned runtime/model artifacts with checksums, explicit download
     consent, quota checks, revocation, purge, worker isolation, and CSP support.
   - Test WebGPU and WASM separately across the supported browser/device matrix;
     never assume WebGPU or persistent model caching.
   - Restrict the pilot to synthetic/public data and reversible drafting tasks.
   **P5 repository status (2026-06-08): DONE.** The self-hosted worker contract,
   manifest validation, immutable revision, asset checksum/size verification,
   explicit consent, quota/device gates, reversible draft insertion, and purge
   path are implemented. The committed pack is unstaged and the feature remains
   off by default. Real-device quality and performance evidence is still
   required for pilot promotion. See [BROWSER_INFERENCE.md](BROWSER_INFERENCE.md).

7. **P6 - harden connection scaling only when load data requires it.**
   - Measure database wait time, active connections, and tenant concurrency
     before adding PgBouncer; do not promise a fixed latency.
   - If transaction pooling is required, redesign tenant context around
     transaction-local settings and prove no query occurs outside the bound
     transaction across HTTP, streaming responses, Celery, commands, and errors.
   - Run cross-tenant adversarial tests through the actual pooler before launch.
   **P6 prerequisite status (2026-06-08): DONE for repository guardrails.**
   `DB_POOL_MODE=direct|session|transaction` now declares the deployment
   contract. Django system checks reject PostgreSQL transaction pooling because
   current tenant isolation depends on session state (`search_path` and
   `app.current_school_id`). Defensive transaction-mode tuning cannot bypass
   that rejection, and failed RLS cleanup now closes the affected connection.
   Use `python manage.py verify_database_pooling` and
   `npm run verify:database-tenancy` for repository verification. Real
   PostgreSQL plus PgBouncer interleaving and load evidence remain required
   before transaction-pooling promotion.

   **Responsive-layout observability status (2026-06-08): DONE for repository
   scope.** The existing CSS-first shell, `100dvh` scroll contract, responsive
   table grammar, and row-detail drawer remain authoritative. A bounded
   observer now reports content-free overflow aggregates through the existing
   RUM path and never compresses fonts or rewrites layout. Visual viewport
   measurements support diagnosis without replacing CSS. See
   [LAYOUT_OBSERVABILITY.md](LAYOUT_OBSERVABILITY.md).

8. **P7 - promotion gate for every intelligence feature.**
   - Require task-specific accuracy, privacy/security review, accessibility,
     tenant isolation, audit coverage, resource budgets, kill switch, rollback,
     degraded behavior, and real operator evidence.
   - Do not claim identical quality, zero collisions, zero latency, fixed RAM,
     or mathematical impossibility in product or architecture documentation.
   **P7 repository status (2026-06-08): DONE.** The canonical
   `config/intelligence_feature_catalog.json` and fail-closed
   `apps.platform_runtime.intelligence_promotion` evaluator cover nine feature
   families and all ten evidence dimensions. Repository evidence can establish
   only `repository_verified`; signed, feature-bound, stage-bound, attributed,
   time-aware evidence is mandatory for pilot or production promotion.
   Catalog stage ceilings prevent experimental families from being promoted
   beyond their approved scope. Browser SLM and voice AI are repository
   implemented but capped at `repository_verified`; both runtime switches are
   disabled by default. See
   [INTELLIGENCE_PROMOTION_GATES.md](INTELLIGENCE_PROMOTION_GATES.md).

### SOT ownership after this audit

| Question | Canonical source |
| --- | --- |
| What work is done/next? | `RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` |
| How does live AI route? | This document |
| What AI surfaces existed in the May snapshot? | `AI_PLATFORM_WIDE_STATUS_2026_05_14.md` |
| What happens when the school/browser is offline? | `LOCAL_HUB_MODE.md` and the current online/offline audit |
| What is the detailed gateway contract? | `docs/architecture/ai_orchestration.md` |

## Health and UI contract

| Field | Meaning |
| --- | --- |
| `posture_mode` | `live_cloud` \| `live_local` \| `guided` \| `unavailable` |
| `posture_label` | Human badge text (AI Center + JS pill) |
| `gateway_tier_chain` | Ordered tiers for this profile |
| `has_live_provider` | Reachability probe succeeded (cloud or Ollama) |

Probes: `apps.portal.ai_provider.probe_ai_provider_reachable()` — LiteLLM `/v1/models` on `online`/`hybrid`, then Ollama.

## Related docs

- Connectivity + offline bundle: `docs/LOCAL_HUB_MODE.md`
- Ollama install/update (edge/on-prem): `docs/OLLAMA_OPERATIONS_AND_UPDATES.md`
- Operator quick start (Render + optional local Ollama dev): `docs/OPERATOR_OLLAMA_AND_RENDER.md`
