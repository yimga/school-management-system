# RunMyCampus — Objection handling (internal)

These are **talking points**, not contract language. Point prospects to the actual deployment, security pack, and DPA as appropriate.

## “We can run this on spreadsheets.”

- Spreadsheets lack **role isolation**, **publish discipline**, and **auditable** change history at scale.  
- Response: *“We keep operational truth in the database with control-plane pages for evidence. Operators see status without opening raw tables.”*

## “We already have a legacy SIS.”

- RunMyCampus can be positioned as the **operational layer** with interop (OneRoster and related modules) where enabled.  
- Do not promise a specific go-live until integration scope is written.  
- Response: *“We align on read/write boundaries in a workshop, then pilot one academic year.”*

## “We’ll build it ourselves.”

- Build cost, security review, and multi-tenant isolation are the hidden multipliers.  
- Response: *“The product already separates tenant context, RLS reset middleware, and evidence surfaces. Rebuilding that is a program, not a project.”*

## “We need 100% feature parity on day one.”

- Parity is a **migration plan**, not a first demo.  
- Response: *“We map must-haves to existing modules, park the rest, and time-box pilot acceptance criteria.”*

## “Your admin looks like Django.”

- **True for Advanced paths.** The product path is CP-first.  
- Response: *“Superusers keep Django for edge cases; day-to-day staff use CCC, portal, and evidence pages.”*

## “Pricing / payment?”

- If Stripe (or other) is not live, say: *“Entitlements and plans are in the data model; billing integration is a deployment option, not a fake button in the demo.”*

## Security / data residency

- Do not invent certifications.  
- Response: *“We can provide architecture notes, RLS/tenant model, and your questionnaire answers; legal review is on your side.”*
