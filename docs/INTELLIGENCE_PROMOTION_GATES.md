# Intelligence promotion gates

**Status:** repository governance complete (2026-06-08). Pilot and production
promotion still require real, reviewed evidence.

## Canonical contract

`config/intelligence_feature_catalog.json` is the feature-family registry.
`apps.platform_runtime.intelligence_promotion` is the only promotion evaluator.
It covers:

- governed AI gateway;
- edge AI;
- marksheet OCR;
- portable tenant RAG;
- local-first synchronization;
- responsive-layout observability;
- predictive at-risk models;
- browser SLM; and
- voice AI.

Every implemented family must provide repository evidence for ten dimensions:
task quality, privacy/security, accessibility, tenant isolation, auditability,
resource budget, kill switch, rollback, degraded behavior, and operator
evidence. Browser SLM and voice AI now have governed repository integrations,
but their catalog ceilings are `repository_verified`. They cannot enter a pilot
until the catalog ceiling is deliberately reviewed and signed external evidence
proves the target model, service, hardware, languages, accessibility, and
resource budgets.

## Stages and evidence

The ordered stages are `disabled`, `repository_verified`, `internal_pilot`,
`limited_production`, and `general_availability`.

Repository paths prove only that the implementation contract exists. They can
never promote a feature to a pilot or production stage. Higher stages require a
signed evidence envelope whose rows:

- are bound to one feature and an explicit approved stage;
- use a known evidence dimension and scope;
- identify the evidence source and reviewer;
- include timezone-aware observation and optional expiry timestamps; and
- pass checksum and HMAC-SHA256 signature verification.

Stage binding prevents limited-production evidence from being reused to claim
general availability. Expired, modified, unknown, unsigned, incomplete, or
lower-scope evidence fails closed.

## Operator workflow

1. Copy reviewed evidence into a JSON body containing `schema_version`,
   `feature_id`, `approved_stage`, and one row for every evidence dimension.
2. Provision `INTELLIGENCE_PROMOTION_SIGNING_KEY` from the deployment secret
   store. Do not commit the key or a signed production envelope.
3. Sign the body:

   `python manage.py sign_intelligence_evidence --body evidence-body.json --output evidence-envelope.json`

4. Evaluate the requested stage:

   `python manage.py verify_intelligence_promotion --feature edge_ai --stage internal_pilot --evidence-file evidence-envelope.json --strict`

5. Remove or rotate the signing key after the controlled signing operation
   according to the deployment secret-rotation policy.

Repository readiness is generated with:

`npm run verify:intelligence-promotion`

The expected repository result is seven eligible implemented families and two
honestly blocked families (`browser_slm`, `voice_ai`). Those blocked rows are
the correct result, not a verifier failure.

## Rollback

Each catalog row names its kill switch, rollback owner, and degraded behavior.
The promotion evaluator does not activate a feature; activation remains with
the owning subsystem. On regression, disable the owning feature first, retain
the evidence/report for audit, and issue new evidence only after remediation.
