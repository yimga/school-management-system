# Live compliance validate-on-write (BR-05)

## Attendance

**Observe (audit):** `school.features.live_compliance_attendance` → platform event `live_compliance_attendance` (`apps/academics/signals.py`), payload includes `attendance_pack_key`.

**Strict (block save):** `school.features.live_compliance_attendance_strict` → validates before save via `Attendance.clean()` + `pre_save`. Rules from `apps/compliance/attendance_region_packs.py` (USA, GBR, CAN, AUS, CMR, DEFAULT) merged with `school.settings.compliance_attendance_pack` overrides.

## Degree enrollment (`StudentDegreeEnrollment`)

**Observe (audit):** `school.features.live_compliance_enrollment` → platform event `live_compliance_enrollment` when pack rules are violated but save is allowed (e.g. active enrollment without `start_date` in USA).

**Strict (block save):** `school.features.live_compliance_enrollment_strict` → `pre_save` on `StudentDegreeEnrollment`. Rules from `apps/compliance/enrollment_region_packs.py`, override via `school.settings.compliance_enrollment_pack`.

**Tests:** `apps/compliance/tests/test_enrollment_region_br05.py`, `test_attendance_region_br05.py`.
