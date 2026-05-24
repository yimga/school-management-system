# RunMyCampus Education OS Kernel

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

## Summary

Defines the kernel-level boundary of the Education OS: 8 platform layers, 15 canonical core entities, 15 runtime context primitives, 27 canonical domain events, kernel-level tenant identity boundary. The kernel is composed of: platform_runtime, tenancy, accounts, schools, security, siteconfig, metadata, global_registries, registries, events, lifecycle, plus the PWA shell (service-worker.js + manifest.json + IndexedDB queues).

## See also

- `docs/generated/edos_kernel_domain_map.{json,md}` — full app-to-layer mapping
- `docs/generated/edos_zero_overhead_runtime_design.{json,md}` — runtime context primitives
- `docs/generated/edos_event_workflow_fabric.{json,md}` — 27-event canonical catalogue
- `docs/generated/edos_tenant_identity_kernel.{json,md}` — kernel-level tenant boundary
- `docs/generated/edos_metadata_configuration_layer.{json,md}` — metadata layer governance

## Architecture correction

A real OS has stable canonical primitives. Tenant variance lives in the metadata layer, not in schema churn. Runtime engines interpret metadata, enforce permissions, validate rules, render forms, route workflows, compile tenant manifests, audit every change, support offline/edge, govern tenant resources, run low-cost micro-solutions, and protect tenant boundaries at app/runtime/database levels.

## PWA-first non-negotiable

Native iOS/Android apps are explicitly DEFERRED. Web + PWA is the launch mobile strategy. Capacitor/Tauri wrapper only after web core stability + first-100-schools + PWA installability proof. Native shell MUST NOT fork product logic when finally introduced.

