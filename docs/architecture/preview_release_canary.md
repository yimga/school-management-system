# Preview / Release and Canary (Section 29.4)

Tenant staging/sandbox schema, config diff viewer, and canary by tenant/country/plan.

**Ref:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md § 29.4.

---

## 1. Config diff API

- **Purpose:** Compare effective policy/settings between two contexts (e.g. current vs staged, or tenant A vs tenant B) for safe rollout.
- **Endpoint (stub):** `GET /api/config-diff/?base=current&compare=staged` or `?school_id=...&compare_school_id=...`. Returns JSON diff of policy keys (no secrets). Requires staff or `config_diff` capability.
- **Implementation:** See `apps.api.config_diff_views` (stub returns structure; full diff can compare get_effective_policy(school_a) vs get_effective_policy(school_b) or current vs saved snapshot).

---

## 2. Tenant staging / sandbox schema

- **Deferred:** Full tenant cloning or staging schema (e.g. `tenant_foo_staging`) is infra/DB work. Document as roadmap: create schema copy, run migrations, point staging URL to staging schema.
- **Minimal:** Feature flag per tenant (e.g. `staging_mode`) that toggles read-only or limited-write behavior; no schema duplicate.

---

## 3. Canary

- **Pattern:** Use existing `is_feature_enabled(school, "CANARY_FEATURE_X")` or plan/addon to enable a feature for a subset of tenants (by country, plan, or explicit allowlist).
- **Document:** Canary rollout = enable feature for one school/country/plan; monitor; then expand. No code change required; use feature flags and policy.
- **Ops:** Set `CONTROL_PLANE_RUNBOOKS_URL` in env so the health dashboard links operators to incident runbooks (see REMAINING_PLAN_AUDIT_GAPS § Control plane runbooks and canary).

---

## 4. Auto rollback on health degradation

- **Deferred:** Automated rollback when error rate or latency degrades (e.g. feature flag auto-off). Document in SRE runbooks; implement in deployment/observability layer.
