# Information Tagging System (Zero Hardcoding)

School-defined tags (e.g. "Scholarship Student", "Early Bird", "Allergy: Nut") without changing the database schema. Tags are data; the AI Nuance Engine reads them to apply discounts and workflows.

## Model

- **InformationTag** (`apps.people.models`): `school`, `name`, `category` (Medical, Financial, Academic, General), `color_hex`, `description`, `is_private`, `is_critical`, `is_active`, `sort_order`.
- **StudentProfile.tags**: ManyToMany to `InformationTag`. Assign tags in Admin or (future) on the student profile UI.

## Security

- **Tenant scoping**: Tags are per-school; School A's tags never appear in School B.
- **Private tags**: `is_private=True` — only users with Admin, IT_ADMIN, or LEADERSHIP (or staff) can see these tags on the student list and profile.

## Tag Manager UI

- **Path**: Site Settings → Customizer → **Tag Manager** (or `/siteconfig/tag-manager/`).
- Create tags with name, category, color, description; optionally mark **Private** and **Critical**.
- **Critical**: When a critical tag is added to a student, a log entry is written; you can extend the signal to create an AccessRequest or notify the Principal (see `apps.people.signals.on_student_critical_tag_added`).

## AI Nuance Engine

- **Context**: For the `fee_discount` (and `tuition_calc`) hook, context includes **`student_tags`**: a list of tag names for the student.
- **JSON-Logic**: Use the **`in`** operator to test membership.

Example — 10% off registration if the student has the "Early Bird" tag:

```json
{
  "if": [
    {"in": ["Early Bird", {"var": "student_tags"}]},
    {"*": [{"var": "fee"}, 0.9]},
    {"var": "fee"}
  ]
}
```

- Create this logic in **Site Settings** → Nuance / Custom logic for the `fee_discount` hook (or equivalent UI where CustomNuance is edited).
- Allowed context keys for `fee_discount`: `fee`, `gpa`, `sibling_count`, `attendance_rate`, `is_staff_child`, **`student_tags`**.

## Student list and Admin

- **Backend student list** (`/backend/` → Students): A **Tags** column shows tag pills (color from `color_hex`). Private tags are hidden unless the user has Admin/Leadership (or staff).
- **Django Admin** → People → Student profile: **Information tags** fieldset with a horizontal multi-select; tags are filtered by the student's school.

## Dispute / workflow (Critical tags)

- When a tag with **is_critical** is added to a student, the signal `on_student_critical_tag_added` in `apps/people/signals.py`:
  1. **Logs** the event (student_id, school_id, tags).
  2. **Creates an AccessRequest** with type **OTHER**, status PENDING, linked to the student (target = StudentProfile). Title/summary describe the critical tag(s); `details` includes `source: "critical_information_tag"`, `student_id`, `school_id`, `tags`, `student_name`.
  3. **Assigns** the request to a school leadership user when possible (first SchoolMembership with role LEADERSHIP, ADMIN, PRINCIPAL, or IT_ADMIN for that school). If none found, `assigned_to` is left null and the request still appears in the Requests dashboard for staff to triage.
- Requests appear in **Requests** (e.g. `/requests/`) for users who can manage requests; assignees see it in their assigned list.

## Global (system) tags (optional)

- The model is school-scoped only. To add platform-wide "system tags" (e.g. "Active", "Graduated") that every school sees, you could add an `InformationTag` variant with `school_id` null and ensure the Tag Manager and admin only offer school tags for assignment; system tags would be read-only defaults per school.
