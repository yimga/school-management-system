# Clever & ClassLink — partnership unblock

**Code unblock:** `apps/interop/clever_classlink_client.py` implements HTTP calls once `CLEVER_CLIENT_ID` + `CLEVER_CLIENT_SECRET` (district) or bearer token from Clever Secure Sync is stored in tenant `ServiceIntegration` or env.

**Business unblock:** Execute district agreement with Clever / ClassLink → obtain API credentials → enter in **District & LMS interop** (future: dedicated “Connect Clever” button writing to `ServiceIntegration`).

**Until then:** OneRoster Bearer + `changesSince` on students + CSV exports = same roster motion.
