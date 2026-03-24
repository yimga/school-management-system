# Clever & ClassLink — native client + district credentials

**Shipped:** `apps/interop/clever_classlink_client.py` — Clever API v3.1 (`/users`, `/schools`, `/sections`), OAuth code exchange (`POST https://clever.com/oauth/tokens`), ClassLink OneRoster ping + `/courses`. **Super console:** `GET/POST /super/native-roster-connectors/` (`super:native_roster_connectors`) for operator probes with district bearer / OAuth fields.

**Tenant path:** Continue to use **District & LMS interop** (OneRoster Bearer, CSV, token rotate) for day-to-day ops; native vendor calls complement that spine when the district provisions Clever/ClassLink tokens.

**Business:** District still executes vendor agreement; this repo supplies the integration surface once tokens exist.
