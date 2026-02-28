# Attendance: QR and RFID integration (optional)

This document describes **integration points** for optional QR code or RFID-based attendance. The core roll-call flow (Take student attendance, Take teacher attendance) does not require QR/RFID; these are extensions for schools that use tap-to-mark or scan-to-mark hardware.

## Current behaviour

- **Student attendance:** Portal path `/portal/attendance/student/` — date + classroom, then mark each student present/absent/late/excused. One-click "Save all present" and "Mark all present" are available.
- **Teacher attendance:** Portal path `/portal/attendance/teacher/` — date, then mark each teacher present/absent/late/on leave.
- **API:** Academics app exposes attendance APIs (e.g. bulk create/update by classroom and date) that can be used by mobile or external systems.

## QR code integration (stub)

- **Possible flow:** A QR code per student (or per device) encodes a stable identifier (e.g. `student_id` or a scoped token). When scanned (e.g. by a teacher’s phone or a kiosk), the app:
  1. Decodes the identifier.
  2. Resolves the student (and optionally classroom/date from context).
  3. Creates or updates an `Attendance` record for today (or the selected date) with status PRESENT (or a configurable default).
- **Integration point:** Add an endpoint, e.g. `POST /api/attendance/scan/` or `POST /portal/attendance/scan/`, that accepts `{"payload": "<decoded_qr_string>", "date": "YYYY-MM-DD", "classroom_id": optional}` and performs the lookup and `Attendance.objects.update_or_create(...)`.
- **Security:** Validate that the requesting user has `attendance.manage` (or equivalent) and that the student belongs to a classroom the user is allowed to mark. Use short-lived or signed tokens in the QR if needed.

## RFID integration (stub)

- **Possible flow:** RFID reader (or a bridge service) sends a card/tag ID to the backend. The backend maps the tag ID to a student (or teacher) via a mapping table (e.g. `StudentRFIDTag` with `student_id`, `tag_id`, `is_active`).
- **Integration point:** Add an endpoint, e.g. `POST /api/attendance/rfid/`, that accepts `{"tag_id": "...", "date": "YYYY-MM-DD", "classroom_id": optional}` and:
  1. Looks up the student (or teacher) for that tag.
  2. Creates or updates the corresponding `Attendance` or `TeacherAttendance` record.
- **Hardware:** Document that the platform expects a HTTP (or message-queue) callback from the RFID bridge; no in-repo driver for specific hardware.

## Feature flag

- A backend feature flag (e.g. `enable_attendance_qr` or `enable_attendance_rfid`) can gate the scan/RFID endpoints and any UI (e.g. “Scan to mark present” button) so that only schools with the feature enabled see and use them.

## Summary

| Item | Status |
|------|--------|
| QR scan endpoint | Stub / not implemented — add when required |
| RFID tag → student mapping | Stub / not implemented — add when required |
| Feature flags for QR/RFID | Optional — add in `backend_feature_flags` when endpoints exist |
| Core roll call (zero-click, mark-all-present, absent parent notify) | Implemented (see Take student/teacher attendance and `notify_parent_on_absence`) |
