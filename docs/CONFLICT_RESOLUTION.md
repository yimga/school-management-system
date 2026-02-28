# Conflict resolution (Plan VII)

## Evals / grades

- **OfflineMarkEntry** with status `conflict` when sync finds an existing Evaluation.
- **resolve_offline_conflict_view**: staff chooses "keep online" or "keep offline"; template `evals/resolve_offline_conflict.html`.
- Admin: `OfflineMarkEntry` changelist; filter by status `conflict` and open resolve URL per entry.

## Attendance

- **Attendance** model has `updated_at` for versioning.
- To extend conflict resolution to attendance: add an **OfflineAttendanceEntry** (or equivalent) model and sync flow that sets status `conflict` when server already has a record for same date/student; add **resolve_attendance_conflict** view following the same pattern as evals (show both versions, choose one).
- API clients should send `X-Client-Updated-At` when updating attendance so the server can return 409 when client is stale.

## CDN / cache

See **DEPLOY_CHECKLIST.md** → "CDN / edge": cache-control headers, asset versioning, recommended CDN in front of app.
