# Positioning — RunMyCampus

## Core frame

**RunMyCampus is a school operating system**, not a loose bundle of disconnected admin screens. One tenant-aware platform covers academics, people, operations, finance hooks, reporting, marketplace extensions, and Studio OS configuration — with **control-plane surfaces** and **read-only evidence** where operators need visibility without CRUD risk.

## Value pillars

1. **Unified system** — Shared shell, tenancy, permissions, and feature entitlements (`Plan.included_features`, school `addons`, feature toggles) reduce context switching.
2. **Operator-first workflows** — Dashboard, Configuration Control Center (CCC), metadata hubs, and report delivery surfaces are designed for day-to-day staff, with **Advanced/Admin** (Django admin) explicitly secondary.
3. **Evidence-driven control** — SiteConfig evidence pages and aggregates support audits and operational reviews without simulating sends, exports, or payments in-product.
4. **Low-click administration** — Prefer product URLs and API contracts; reserve Django admin for edge CRUD and platform operators.

## Language to use (and avoid)

- Prefer: *tenant*, *operator*, *control plane*, *evidence*, *entitlements*, *scheduled delivery*.
- Avoid implying: fake customers, guaranteed compliance outcomes, or payment capture inside the core app (billing integration is out of scope for this repo slice).

## Proof in the product

- CCC: `siteconfig:console_domains_hub` (manager host).
- Evidence examples: report output history, tenant report schedules, config mutation audit (read-only).
- Plan summary (read-only): `siteconfig:billing_plan_readonly` at `/siteconfig/billing/plan/` on tenant hosts.
