# Parent contact: single source of truth

**Status:** Policy (Phase 1.2)  
**Plan:** [PLAN_ENROLLMENT_FEE_IMPROVEMENTS.md](./PLAN_ENROLLMENT_FEE_IMPROVEMENTS.md)

## Rule

- **Preferred source:** Use **`StudentGuardian.phone`** and **`StudentGuardian.email`** for parent/guardian contact (reminders, notifications, display).
- **Fallback:** When there is no guardian link, or when `StudentGuardian.phone` / `StudentGuardian.email` are empty, use **`StudentProfile.parent_phone`** (and, if needed, the guardian user’s email from the linked `User`).
- **One-way sync (optional):** When saving a `StudentGuardian` with a non-empty `phone`, if the linked student’s `parent_phone` is empty, the system may set `student.parent_phone = guardian.phone` so the fallback stays in sync. This keeps legacy and reminder code that still reads `student.parent_phone` correct.

## Where contact is used

- Payment reminders (finance): prefer `guardian.email` and `guardian.phone` (see `apps/finance/tasks.py`).
- Onboarding / portal: guardian link stores `email` and `phone`; backend “Create Student” syncs form values to `StudentGuardian` (Phase 1.1).
- Admin / display: prefer guardian contact when available; `StudentProfile.parent_phone` is documented as fallback.

## Adding new features

When sending emails or SMS to a guardian, resolve contact in this order:

1. `StudentGuardian.email` / `StudentGuardian.phone` for the linked guardian.
2. If empty, `guardian_user.email` (User) and `StudentProfile.parent_phone` for that student.
