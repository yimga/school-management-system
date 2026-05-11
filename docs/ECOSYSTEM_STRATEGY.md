# Ecosystem strategy — the "AWS / Shopify / Salesforce of education" lane

The product mandate is to compete with Stripe (developer-loved), Shopify (App Store),
and Salesforce (AppExchange) — not just with PowerSchool / Veracross / Alma. That
positioning is half engineering and half go-to-market. This doc covers the engineering
half: public API, developer portal, app/plugin marketplace, partner program scaffolding,
and ROI calculator architecture.
Last reviewed: 2026-05-11.

---

## 1. The three pillars

| Pillar | Stripe analogue | Shopify analogue | Salesforce analogue | Our v0 status |
|---|---|---|---|---|
| **Public API + DX** | `stripe.com/docs` | `shopify.dev/api` | Salesforce REST API | Endpoints exist, OpenAPI surface missing |
| **App/Plugin marketplace** | Stripe Apps | Shopify App Store | AppExchange | Not started |
| **Partner program** | Stripe Partners | Shopify Partners | Salesforce ISVForce | Not started |

Each requires engineering primitives the others depend on. We sequence the build so
each unlocks the next.

## 2. Engineering primitives needed

### 2.1 Public API surface (foundation)
- **Versioned base URL**: `/api/v1/` is partially wired; commit to a versioning policy (URL major, header minor) and document deprecation windows (12 months minimum).
- **OpenAPI spec generated from code**: install `drf-spectacular`, expose `/schema/`, `/schema/swagger-ui/`, `/schema/redoc/`. Spec must be the source of truth for SDKs and docs.
- **Authentication tiers**:
  - **Session cookie** for first-party browser
  - **API key** (`apps/apicenter/` exists) for server-to-server tenant integrations
  - **OAuth 2.0** with PKCE for third-party apps installed by tenants (NEW — required for marketplace)
- **Rate limits**: per-key + per-tenant tiers; documented limits visible at `dev.runmycampus.com/api/limits`.
- **Idempotency keys**: `Idempotency-Key` header support on all POST endpoints (Stripe pattern).
- **Webhook system**: HMAC-SHA256 signatures, retries with exponential backoff (Stripe schedule: 5min, 1h, 6h, 24h, 7d), idempotent event ids, dashboard for delivery log. `WebhookSubscription` model exists; productize.

### 2.2 Developer portal
- **dev.runmycampus.com** (new public surface; separate from runmycampus.com).
- Sections:
  - **Getting Started** — auth, first call, first webhook (3-page quickstart)
  - **API reference** — generated from OpenAPI (Redoc embedded)
  - **Webhooks** — event catalog with example payloads
  - **SDKs** — Python, Node.js, PHP (auto-generated from OpenAPI via `openapi-generator`)
  - **Recipes** — "sync from PowerSchool", "send daily attendance webhook to Slack"
  - **Changelog** — versioned, RSS feed
  - **Status** — embed `status.runmycampus.com`
  - **Support** — community Discord + commercial support tiers

### 2.3 App/Plugin marketplace
This is the big one — it differentiates from PowerSchool (closed) and lifts the moat
into network-effects territory.

**Model**: tenants install third-party apps that get scoped OAuth 2.0 grants to specific
data scopes (`students:read`, `attendance:write`, `grades:read`, `webhooks:manage`).
Each app declares scopes; the tenant admin reviews and approves on install.

**Required primitives**:
- `MarketplaceApp` model: publisher, name, description, logo, scopes, install_url, oauth_redirect_uri, webhook_url, pricing_model, listing_status.
- `AppInstallation`: per-tenant install with granted scopes + revocation.
- `AppReview`: per-tenant rating + comment.
- `AppSubscription`: billing relationship if app is paid (revenue share 70/30 publisher/platform per Stripe Apps).
- **Sandbox tenant**: every publisher gets a free sandbox tenant they can develop against.
- **App submission flow**: form → automated checks (manifest validity, scope minimization, webhook reachability) → human review → publish.
- **Embedded app surface**: optional `<iframe>` host with postMessage shim for apps that want UI in our portal (Shopify App Bridge pattern).

**Marketplace categories** (initial 6):
1. SIS migration tools (PowerSchool sync, Skyward sync, etc.)
2. Communication (Slack/Teams bridges, Twilio alternatives, custom SMS)
3. Payments (regional gateways beyond our defaults)
4. Reporting (custom report builders, Excel writebacks, BI connectors)
5. Learning add-ons (ClassDojo bridge, Khan Academy integration, custom LMS)
6. Vertical industry (boarding tools, faith-based add-ons, athletics, transport)

### 2.4 Partner program
- **Tiers**: Affiliate / Implementation / Technology / Strategic.
- **Affiliate**: % revenue share on referred tenants (60/40 platform/affiliate first year, then 80/20 platform/affiliate).
- **Implementation**: trained consultants who onboard tenants on our behalf; certified via `partners.runmycampus.com/training`.
- **Technology**: companies that ship apps via the marketplace; revenue share above.
- **Strategic**: co-marketing + product-roadmap influence.
- Required: directory site (partners.runmycampus.com), self-service application form, partner portal showing pipeline + commissions, partner-specific Slack/Discord.

### 2.5 ROI calculator
Sales tool, not engineering core, but lives at runmycampus.com/roi.
- Inputs: # students, # teachers, current SIS spend, time spent on attendance/grading/comms.
- Outputs: estimated annual saving, payback period, tier recommendation, "talk to sales" CTA.
- Implementation: static React/Vue micro-app served from marketing surface.

## 3. Sequencing (recommended 18-month plan)

### Phase 1 — API foundation (0-3 months)
1. Install drf-spectacular; expose `/api/v1/schema/`, `/api/v1/docs/`.
2. Audit every existing endpoint for tenant scoping + RLS + rate-limit + idempotency-key support.
3. Document the webhook event catalog (lock event names; never rename).
4. Ship signed webhook delivery + retry log.
5. Publish dev.runmycampus.com (just OpenAPI Redoc + getting-started + webhook docs).

### Phase 2 — OAuth + SDKs (3-6 months)
1. Wire `oauth2_provider` (likely already in INSTALLED_APPS — verify).
2. Define scope vocabulary (`students:read`, `attendance:write`, etc.).
3. Generate Python + Node.js SDKs from OpenAPI; publish to PyPI + npm.
4. Sandbox tenant infrastructure.
5. First three "official" apps built in-house to validate the surface (e.g. Slack notifications, Google Calendar sync, Twilio SMS).

### Phase 3 — Marketplace beta (6-12 months)
1. `MarketplaceApp` + `AppInstallation` + `AppReview` models.
2. Submission flow + automated checks.
3. Tenant-facing app directory in the admin (`/admin/apps/`).
4. Revenue share via Stripe Connect.
5. Embedded app surface (postMessage shim + iframe host).
6. Onboard 10-20 partners; soft-launch marketplace.

### Phase 4 — Partner program (9-15 months, overlapping)
1. partners.runmycampus.com.
2. Certification curriculum + exam.
3. Partner portal with pipeline + commissions.
4. Affiliate-link tracking integrated with billing.

### Phase 5 — Scale (15-18 months+)
1. SDKs for PHP, Ruby, Go.
2. Webhooks v2: filtering, transformation, replay.
3. GraphQL surface (graphene-django is already in requirements).
4. Public roadmap voting.
5. Quarterly developer conference (virtual first, then in-person).

## 4. What we already have that helps

- `apps/apicenter/` API key model + governance.
- `apps/siteconfig/WebhookSubscription` + delivery infra.
- `graphene-django` in requirements (GraphQL surface latent).
- `apps/integrations/` namespace (per `INTEGRATION_API_CENTER_UNIFIED.md` doc).
- `apps/policies/BlueprintPack` — the "policy pack" pattern generalizes naturally to "marketplace app manifest".
- The Render PR-deploy pattern works for sandbox tenants.

## 5. What we'd need to NOT do

- **Don't rebuild Django admin for the marketplace**. Use it for staff-facing review queues; build a separate `/dev/` and `/apps/` admin surface for publishers and tenant admins.
- **Don't ship a marketplace before the API is stable**. v1 endpoints must be versioned and supported for ≥12 months before publishers will build against them. Once shipped, breaking changes are a multi-year migration.
- **Don't promise revenue share without Stripe Connect**. Manual split payouts won't scale past ~20 apps.
- **Don't enter the marketplace race without a moat**. The moat is multi-tenant data + global currency/locale/regional-system support that competitors lack. Lead with the moat in publisher pitches.

## 6. Open questions

- Do we monetize the marketplace v0 or keep it free to bootstrap supply? Stripe Apps was free initially; Shopify charges 15% for first $1M then 20%.
- Sandbox tenants — do they get full feature parity or feature-gated? Shopify gives full parity to development stores.
- App-publisher onboarding: open vs invite-only? Salesforce AppExchange is curated invite-only; Shopify is open with review. Recommend invite-only v0 to control quality, transition to open after 50 apps.
- Pricing surface for marketplace apps: subscription only, or one-time + subscription + metered? Stripe supports all three.

## 7. Adjacent ideas worth tracking

- **`runmycampus.com/case-studies` library**: lock at least 5 video case studies before scaling sales.
- **runmycampus.com/integrations directory**: SEO-rich destination listing every integration we natively support; doubles as developer-onboarding lead-magnet.
- **Annual State of K-12 SaaS report**: data-rich PDF using anonymized platform metrics. Becomes the press hook.
- **University-of-RunMyCampus**: free certification for school admins + partners; lifts NPS and creates a talent pipeline our customers will hire from.
