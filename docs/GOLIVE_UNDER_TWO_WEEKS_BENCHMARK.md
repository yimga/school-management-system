# Go-live &lt;2 weeks — benchmark (wedge 1)

**Stopwatch start:** Tenant provisioned (school record + admin user invited).  
**Stopwatch end:** First meaningful use — e.g. attendance taken, fee invoice issued, or grade entered.

**Target:** ≤ 10 business days for international K–12 template with Launch Studio checklist complete.

Record each production go-live duration; publish anonymized p50/p90 in marketing when N≥5.

## N29 measured setup (structural closure)

| Field | Value |
|-------|--------|
| **Metric** | Wall-clock minutes from tenant provisioned → first meaningful use (attendance / invoice / grade). |
| **Where to record** | Internal spreadsheet or CRM; optional `notes` on school go-live ticket. |
| **Staging proof** | Run Launch Studio checklist end-to-end on staging; capture timestamp delta; attach to release sign-off ([launch_studio_checklist.md](launch_studio_checklist.md) §4). |
| **Product bar** | N≥5 production anonymized samples before marketing claim (p50/p90). |

**Code/tests:** `test_sot_0155_signup_region_deep_link.py` (choose region → create school). Extend with timing only when product adds explicit telemetry.
