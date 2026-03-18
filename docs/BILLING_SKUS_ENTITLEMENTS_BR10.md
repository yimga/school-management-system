# Billing SKUs & entitlements (BR-10)

| SKU | Maps to | Notes |
|-----|---------|-------|
| **core_sis** | School plan baseline | SIS, attendance, grades core |
| **interop_plus** | `addons` / plan | OneRoster depth, API Center, webhooks |
| **intelligence_plus** | `addons` | EWS, NL query (super), analytics premium |
| **marketplace_sandbox** | Feature | Install-to-sandbox |
| **live_compliance** | `School.features.live_compliance_attendance` | Validate-on-write flags |

**Rule:** Sales quote must reference **shipped** modules only; update this table when entitlements code changes (`plans_entitlements`, `School.addons`).
