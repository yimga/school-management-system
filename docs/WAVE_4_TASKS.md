# Wave 4 — Teacher Attendance Core (done)

| Sub-item | Description | Status |
|----------|-------------|--------|
| W4-1 | Zero-click attendance (mark-all-present by default, one click to save) | ✅ |
| W4-2 | Seating chart view or link | ✅ |
| W4-3 | Mark-all-present action | ✅ |
| W4-4 | Absent parent notification (trigger email/SMS when absent) | ✅ |
| W4-5 | Optional QR or RFID integration point (document or stub) | ✅ |

## Implementation notes

- **W4-1 / W4-3:** Student and teacher roll call already default to Present. Added **Save all present** button on both `roll_call_student.html` and `roll_call_teacher.html` that sets all dropdowns to Present and submits the form in one click.
- **W4-2:** New view `seating_chart_view` at `/portal/attendance/seating-chart/` with optional `?classroom=id`. Template `portal/seating_chart.html` shows class selector and a “Coming soon” placeholder for visual layout. **Seating chart** link added on the student attendance page (next to Load).
- **W4-4:** Already implemented: `apps/academics/signals.py` — `on_attendance_saved` creates a Notification for linked guardians when status is ABSENT, gated by `backend_feature_flags.notify_parent_on_absence`.
- **W4-5:** `docs/ATTENDANCE_QR_RFID.md` documents optional QR and RFID integration points (stub endpoints, feature flags, security).

## Code refs

- `templates/portal/roll_call_student.html`, `templates/portal/roll_call_teacher.html` — Mark all present + Save all present.
- `apps/portal/views.py` — `seating_chart_view`.
- `apps/portal/urls.py` — `path("attendance/seating-chart/", seating_chart_view, name="seating_chart")`.
- `templates/portal/seating_chart.html` — Seating chart placeholder.
- `apps/academics/signals.py` — Absent parent notification.
- `docs/ATTENDANCE_QR_RFID.md` — QR/RFID stub.
